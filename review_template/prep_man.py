#! /usr/bin/env python
import logging
import pprint
from pathlib import Path

import bibtexparser
import pandas as pd
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

from review_template import prep
from review_template.review_manager import RecordState

report_logger = logging.getLogger("review_template_report")
logger = logging.getLogger("review_template")
pp = pprint.PrettyPrinter(indent=4, width=140)


def prep_man_stats(REVIEW_MANAGER) -> None:
    from review_template.review_manager import Process, ProcessType

    REVIEW_MANAGER.notify(Process(ProcessType.explore))
    # TODO : this function mixes return values and saving to files.
    logger.info(f"Load {REVIEW_MANAGER.paths['MAIN_REFERENCES_RELATIVE']}")
    bib_db = REVIEW_MANAGER.load_bib_db()

    logger.info("Calculate statistics")
    stats: dict = {"ENTRYTYPE": {}}
    overall_types: dict = {"ENTRYTYPE": {}}
    prep_man_hints = []
    origins = []
    crosstab = []
    for record in bib_db.entries:
        if RecordState.md_imported != record["status"]:
            if record["ENTRYTYPE"] in overall_types["ENTRYTYPE"]:
                overall_types["ENTRYTYPE"][record["ENTRYTYPE"]] = (
                    overall_types["ENTRYTYPE"][record["ENTRYTYPE"]] + 1
                )
            else:
                overall_types["ENTRYTYPE"][record["ENTRYTYPE"]] = 1

        if RecordState.md_needs_manual_preparation != record["status"]:
            continue

        if record["ENTRYTYPE"] in stats["ENTRYTYPE"]:
            stats["ENTRYTYPE"][record["ENTRYTYPE"]] = (
                stats["ENTRYTYPE"][record["ENTRYTYPE"]] + 1
            )
        else:
            stats["ENTRYTYPE"][record["ENTRYTYPE"]] = 1

        if "man_prep_hints" in record:
            hints = record["man_prep_hints"].split(";")
            prep_man_hints.append(hints)
            for hint in hints:
                if "change-score" in hint:
                    continue
                # Note: if something causes the needs_manual_preparation
                # it is caused by all origins
                for orig in record.get("origin", "NA").split(";"):
                    crosstab.append([orig[: orig.rfind("/")], hint])

        origins.append(
            [x[: x.rfind("/")] for x in record.get("origin", "NA").split(";")]
        )

    crosstab_df = pd.DataFrame(crosstab, columns=["origin", "hint"])

    tabulated = pd.pivot_table(
        crosstab_df[["origin", "hint"]],
        index=["origin"],
        columns=["hint"],
        aggfunc=len,
        fill_value=0,
        margins=True,
    )
    # .sort_index(axis='columns')
    tabulated.sort_values(by=["All"], ascending=False, inplace=True)
    # Transpose because we tend to have more error categories than search files.
    tabulated = tabulated.transpose()
    print(tabulated)
    logger.info("Writing data to file: manual_preparation_statistics.csv")
    tabulated.to_csv("manual_preparation_statistics.csv")

    # TODO : these should be combined in one dict and returned:
    print("Entry type statistics overall:")
    pp.pprint(overall_types["ENTRYTYPE"])

    print("Entry type statistics (needs_manual_preparation):")
    pp.pprint(stats["ENTRYTYPE"])

    return


def extract_needs_prep_man(REVIEW_MANAGER) -> None:
    from review_template.review_manager import Process, ProcessType

    REVIEW_MANAGER.notify(Process(ProcessType.explore))
    logger.info(f"Load {REVIEW_MANAGER.paths['MAIN_REFERENCES_RELATIVE']}")
    bib_db = REVIEW_MANAGER.load_bib_db()

    bib_db.entries = [
        record
        for record in bib_db.entries
        if RecordState.md_needs_manual_preparation == record["status"]
    ]

    Path("prep_man").mkdir(exist_ok=True)
    Path("prep_man/search").mkdir(exist_ok=True)

    with open("prep_man/references_need_prep_man_export.bib", "w") as fi:
        fi.write(bibtexparser.dumps(bib_db))

    logger.info("Load origins")

    origin_list = []
    for record in bib_db.entries:
        for orig in record.get("origin", "NA").split(";"):
            origin_list.append(orig.split("/"))

    search_results_list: dict = {}
    for file, id in origin_list:
        if file in search_results_list:
            search_results_list[file].append(id)
        else:
            search_results_list[file] = [id]

    for file, id_list in search_results_list.items():
        search_db = BibDatabase()
        print(file)
        with open(REVIEW_MANAGER.paths["SEARCHDIR"] / file) as sr_db_path:
            sr_db = BibTexParser(
                customization=convert_to_unicode,
                ignore_nonstandard_types=False,
                common_strings=True,
            ).parse_file(sr_db_path, partial=True)
        for id in id_list:
            orig_rec = [r for r in sr_db.entries if id == r["ID"]][0]
            search_db.entries.append(orig_rec)
        print(len(search_db.entries))

        with open("prep_man/search/" + file, "w") as fi:
            fi.write(bibtexparser.dumps(search_db))

    return


def get_data(REVIEW_MANAGER) -> dict:
    from review_template.review_manager import RecordState, ProcessType, Process

    REVIEW_MANAGER.notify(Process(ProcessType.prep_man))

    record_state_list = REVIEW_MANAGER.get_record_state_list()
    nr_tasks = len(
        [
            x
            for x in record_state_list
            if str(RecordState.md_needs_manual_preparation) == x[1]
        ]
    )

    all_ids = [x[0] for x in record_state_list]

    PAD = min((max(len(x[0]) for x in record_state_list) + 2), 35)

    items = REVIEW_MANAGER.read_next_record(
        conditions={"status": str(RecordState.md_needs_manual_preparation)}
    )

    md_prep_man_data = {
        "nr_tasks": nr_tasks,
        "items": items,
        "all_ids": all_ids,
        "PAD": PAD,
    }
    logger.debug(pp.pformat(md_prep_man_data))
    return md_prep_man_data


def set_data(REVIEW_MANAGER, record, PAD: int = 40) -> None:
    from review_template.review_manager import RecordState

    # TODO: log details for processing_report

    record.update(status=RecordState.md_prepared)
    record.update(metadata_source="MAN_PREP")
    record = prep.drop_fields(record)

    REVIEW_MANAGER.update_record_by_ID(record)

    # bib_db = REVIEW_MANAGER.load_bib_db()
    # REVIEW_MANAGER.save_bib_db(bib_db)
    git_repo = REVIEW_MANAGER.get_repo()
    git_repo.index.add([str(REVIEW_MANAGER.paths["MAIN_REFERENCES_RELATIVE"])])

    # TODO : maybe update the IDs when we have a replace_record procedure
    # set_IDs
    # that can handle changes in IDs
    # record.update(
    #     ID=REVIEW_MANAGER.generate_ID_blacklist(
    #         record, all_ids, record_in_bib_db=True, raise_error=False
    #     )
    # )
    # all_ids.append(record["ID"])

    return
