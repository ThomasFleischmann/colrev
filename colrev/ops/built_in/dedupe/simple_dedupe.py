#! /usr/bin/env python
"""Simple dedupe functionality (based on similarity thresholds) for small samples"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd
import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.built_in.dedupe.utils
import colrev.ops.built_in.pdf_prep.metadata_valiation
import colrev.record
import colrev.ui_cli.cli_colors as colors

if TYPE_CHECKING:
    import colrev.ops.dedupe

# pylint: disable=too-many-arguments
# pylint: disable=too-few-public-methods


@zope.interface.implementer(colrev.env.package_manager.DedupePackageEndpointInterface)
@dataclass
class SimpleDedupe(JsonSchemaMixin):
    """Simple duplicate identification (for small sample sizes)"""

    @dataclass
    class SimpleDedupeSettings(JsonSchemaMixin):
        endpoint: str
        merging_non_dup_threshold: float = 0.7
        merging_dup_threshold: float = 0.95

        _details = {
            "merging_non_dup_threshold": {
                "tooltip": "Threshold: record pairs with a similarity "
                "below this threshold are considered non-duplicates"
            },
            "merging_dup_threshold": {
                "tooltip": "Threshold: record pairs with a similarity "
                "above this threshold are considered duplicates"
            },
        }

    settings_class = SimpleDedupeSettings

    def __init__(
        self,
        *,
        dedupe_operation: colrev.ops.dedupe.Dedupe,  # pylint: disable=unused-argument
        settings: dict,
    ):

        self.settings = from_dict(data_class=self.settings_class, data=settings)

        assert self.settings.merging_non_dup_threshold >= 0.0
        assert self.settings.merging_non_dup_threshold <= 1.0
        assert self.settings.merging_dup_threshold >= 0.0
        assert self.settings.merging_dup_threshold <= 1.0

    def __calculate_similarities_record(
        self, *, dedupe_operation: colrev.ops.dedupe.Dedupe, records_df: pd.DataFrame
    ) -> pd.DataFrame:

        # Note: per definition, similarities are needed relative to the last row.
        records_df["similarity"] = 0
        records_df["details"] = 0
        sim_col = records_df.columns.get_loc("similarity")  # type: ignore
        details_col = records_df.columns.get_loc("details")  # type: ignore
        for base_record_i in range(0, records_df.shape[0]):
            sim_details = colrev.record.Record.get_similarity_detailed(
                df_a=records_df.iloc[base_record_i], df_b=records_df.iloc[-1]
            )
            dedupe_operation.review_manager.report_logger.debug(
                f"Similarity score: {sim_details['score']}"
            )
            dedupe_operation.review_manager.report_logger.debug(sim_details["details"])

            records_df.iloc[base_record_i, sim_col] = sim_details["score"]
            records_df.iloc[base_record_i, details_col] = sim_details["details"]
        # Note: return all other records (not the comparison record/first row)
        # and restrict it to the ID, similarity and details
        id_col = records_df.columns.get_loc("ID")  # type: ignore
        sim_col = records_df.columns.get_loc("similarity")  # type: ignore
        details_col = records_df.columns.get_loc("details")  # type: ignore
        return records_df.iloc[:, [id_col, sim_col, details_col]]

    def append_merges(
        self, *, dedupe_operation: colrev.ops.dedupe.Dedupe, batch_item: dict
    ) -> dict:

        dedupe_operation.review_manager.logger.debug(
            f'append_merges {batch_item["record"]}'
        )

        records_df = batch_item["queue"]

        # if the record is the first one added to the records
        # (in a preceding processing step), it can be propagated
        # if len(batch_item["queue"]) < 2:
        if len(records_df.index) < 2:
            return {
                "ID1": batch_item["record"],
                "ID2": "NA",
                "similarity": 1,
                "decision": "no_duplicate",
            }

        # df to get_similarities for each other record
        records_df = self.__calculate_similarities_record(
            dedupe_operation=dedupe_operation, records_df=records_df
        )
        # drop the first row (similarities are calculated relative to the last row)
        records_df = records_df.iloc[:-1, :]
        # if batch_item['record'] == 'AdamsNelsonTodd1992':
        #     records_df.to_csv('last_similarities.csv')

        max_similarity = records_df.similarity.max()

        # TODO: it may not be sufficient to consider
        # the record with the highest similarity

        ret = {}
        if max_similarity <= self.settings.merging_non_dup_threshold:
            # Note: if no other record has a similarity exceeding the threshold,
            # it is considered a non-duplicate (in relation to all other records)
            dedupe_operation.review_manager.logger.debug(
                f"max_similarity ({max_similarity})"
            )
            ret = {
                "ID1": batch_item["record"],
                "ID2": "NA",
                "similarity": max_similarity,
                "decision": "no_duplicate",
            }

        elif (
            self.settings.merging_non_dup_threshold
            < max_similarity
            < self.settings.merging_dup_threshold
        ):

            other_id = records_df.loc[records_df["similarity"].idxmax()]["ID"]
            dedupe_operation.review_manager.logger.debug(
                f"max_similarity ({max_similarity}): {batch_item['record']} {other_id}"
            )
            details = records_df.loc[records_df["similarity"].idxmax()]["details"]
            dedupe_operation.review_manager.logger.debug(details)
            # record_a, record_b = sorted([ID, record["ID"]])
            msg = (
                f'{batch_item["record"]} - {other_id}'.ljust(35, " ")
                + f"  - potential duplicate (similarity: {max_similarity})"
            )
            dedupe_operation.review_manager.report_logger.info(msg)
            dedupe_operation.review_manager.logger.info(msg)
            ret = {
                "ID1": batch_item["record"],
                "ID2": other_id,
                "similarity": max_similarity,
                "decision": "potential_duplicate",
            }

        else:  # max_similarity >= self.settings.merging_dup_threshold:
            # note: the following status will not be saved in the bib file but
            # in the duplicate_tuples.csv (which will be applied to the bib file
            # in the end)
            other_id = records_df.loc[records_df["similarity"].idxmax()]["ID"]
            dedupe_operation.review_manager.logger.debug(
                f"max_similarity ({max_similarity}): {batch_item['record']} {other_id}"
            )
            details = records_df.loc[records_df["similarity"].idxmax()]["details"]
            dedupe_operation.review_manager.logger.debug(details)
            msg = (
                f'Dropped duplicate: {batch_item["record"]} (duplicate of {other_id})'
                + f" (similarity: {max_similarity})\nDetails: {details}"
            )
            dedupe_operation.review_manager.report_logger.info(msg)
            dedupe_operation.review_manager.logger.info(msg)
            ret = {
                "ID1": batch_item["record"],
                "ID2": other_id,
                "similarity": max_similarity,
                "decision": "duplicate",
            }
        return ret

    def __get_dedupe_data(self, *, dedupe_operation: colrev.ops.dedupe.Dedupe) -> dict:

        records_headers = dedupe_operation.review_manager.dataset.load_records_dict(
            header_only=True
        )
        record_header_list = list(records_headers.values())

        ids_to_dedupe = [
            x["ID"]
            for x in record_header_list
            if x["colrev_status"] == colrev.record.RecordState.md_prepared
        ]
        processed_ids = [
            x["ID"]
            for x in record_header_list
            if x["colrev_status"]
            not in [
                colrev.record.RecordState.md_imported,
                colrev.record.RecordState.md_prepared,
                colrev.record.RecordState.md_needs_manual_preparation,
            ]
        ]
        if len(ids_to_dedupe) > 20:
            if not dedupe_operation.review_manager.force_mode:
                dedupe_operation.review_manager.logger.warning(
                    "Simple duplicate identification selected despite sufficient sample size.\n"
                    "Active learning algorithms may perform better:\n"
                    f"{colors.ORANGE}   colrev settings -m 'dedupe.scripts="
                    '[{"endpoint": "active_learning_training"},'
                    f'{{"endpoint": "active_learning_automated"}}]\'{colors.END}'
                )
                raise colrev_exceptions.CoLRevException(
                    "To use simple duplicate identification, use\n"
                    f"{colors.ORANGE}    colrev dedupe --force{colors.END}"
                )

        nr_tasks = len(ids_to_dedupe)
        dedupe_data = {
            "nr_tasks": nr_tasks,
            "queue": processed_ids + ids_to_dedupe,
            "items_start": len(processed_ids),
        }
        dedupe_operation.review_manager.logger.debug(
            dedupe_operation.review_manager.p_printer.pformat(dedupe_data)
        )
        return dedupe_data

    def __get_record_batch(
        self, *, dedupe_operation: colrev.ops.dedupe.Dedupe, dedupe_data: dict
    ) -> list:
        records = dedupe_operation.review_manager.dataset.load_records_dict()

        # Note: Because we only introduce individual (non-merged records),
        # there should be no semicolons in colrev_origin!
        records_queue = [
            record
            for ID, record in records.items()
            if ID in dedupe_data["queue"]  # type: ignore
        ]

        records_df_queue = pd.DataFrame.from_records(records_queue)
        records = dedupe_operation.prep_records(records_df=records_df_queue)
        # dedupe.review_manager.p_printer.pprint(records.values())
        records_df = pd.DataFrame(records.values())

        items_start = dedupe_data["items_start"]
        batch_data = []
        for i in range(items_start, len(dedupe_data["queue"])):  # type: ignore
            batch_data.append(
                {
                    "record": dedupe_data["queue"][i],  # type: ignore
                    "queue": records_df.iloc[: i + 1],
                }
            )
        return batch_data

    def __process_potential_duplicates(
        self, *, dedupe_operation: colrev.ops.dedupe.Dedupe, dedupe_batch_results: list
    ) -> list:
        potential_duplicates = [
            r for r in dedupe_batch_results if "potential_duplicate" == r["decision"]
        ]

        records = dedupe_operation.review_manager.dataset.load_records_dict()
        records = dedupe_operation.prep_records(
            records_df=pd.DataFrame.from_records(list(records.values()))
        )
        # dedupe.review_manager.p_printer.pprint(records.values())
        records_df = pd.DataFrame(records.values())

        keys = list(records_df.columns)
        for key_to_drop in [
            "ID",
            "colrev_origin",
            "colrev_status",
            "colrev_id",
            "container_title",
        ]:
            if key_to_drop in keys:
                keys.remove(key_to_drop)

        n_match, n_distinct = 0, 0
        for potential_duplicate in potential_duplicates:
            rec1 = records_df.loc[records_df["ID"] == potential_duplicate["ID1"], :]
            rec2 = records_df.loc[records_df["ID"] == potential_duplicate["ID2"], :]

            record_pair = [rec1.to_dict("records")[0], rec2.to_dict("records")[0]]

            user_input = (
                colrev.ops.built_in.dedupe.utils.console_duplicate_instance_label(
                    record_pair, keys, True, "TODO", n_match, n_distinct, []
                )
            )

            # set potential_duplicates
            if "y" == user_input:
                potential_duplicate["decision"] = "duplicate"
                n_match += 1
            if "n" == user_input:
                potential_duplicate["decision"] = "no_duplicate"
                n_distinct += 1

        return potential_duplicates

    # TODO : add similarity function as a parameter?
    def run_dedupe(self, dedupe_operation: colrev.ops.dedupe.Dedupe) -> None:
        """Pairwise identification of duplicates based on static similarity measure

        This procedure should only be used in small samples on which active learning
        models cannot be trained.
        """

        # default='warn'
        pd.options.mode.chained_assignment = None  # type: ignore  # noqa

        dedupe_operation.review_manager.logger.info("Simple duplicate identification")
        dedupe_operation.review_manager.logger.info(
            "Pairwise identification of duplicates based on static similarity measure"
        )

        dedupe_data = self.__get_dedupe_data(dedupe_operation=dedupe_operation)

        # the queue (order) matters for the incremental merging (make sure that each
        # additional record is compared to/merged with all prior records in
        # the queue)

        batch_data = self.__get_record_batch(
            dedupe_operation=dedupe_operation, dedupe_data=dedupe_data
        )

        dedupe_batch_results = []
        for item in batch_data:
            dedupe_batch_results.append(
                self.append_merges(dedupe_operation=dedupe_operation, batch_item=item)
            )

        # dedupe_batch[-1]['queue'].to_csv('last_records.csv')

        dedupe_operation.apply_merges(
            results=dedupe_batch_results, complete_dedupe=True
        )

        dedupe_operation.review_manager.logger.info("Completed application of merges")

        dedupe_operation.review_manager.create_commit(
            msg="Merge duplicate records",
            script_call="colrev dedupe",
        )

        potential_duplicates = self.__process_potential_duplicates(
            dedupe_operation=dedupe_operation, dedupe_batch_results=dedupe_batch_results
        )

        # apply:
        dedupe_operation.apply_merges(results=potential_duplicates)

        # add and commit
        dedupe_operation.review_manager.dataset.add_record_changes()
        dedupe_operation.review_manager.create_commit(
            msg="Manual labeling of remaining duplicate candidates",
            manual_author=False,
            script_call="colrev dedupe",
        )


if __name__ == "__main__":
    pass
