#! /usr/bin/env python
"""SearchSource: DBLP"""
from __future__ import annotations

import html
import json
import re
import typing
from dataclasses import dataclass
from datetime import datetime
from multiprocessing import Lock
from pathlib import Path
from sqlite3 import OperationalError
from typing import TYPE_CHECKING

import requests
import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.built_in.search_sources.utils as connector_utils
import colrev.ops.search
import colrev.record
import colrev.settings
import colrev.ui_cli.cli_colors as colors

if TYPE_CHECKING:
    import colrev.ops.prep

# pylint: disable=unused-argument
# pylint: disable=duplicate-code


@zope.interface.implementer(
    colrev.env.package_manager.SearchSourcePackageEndpointInterface
)
@dataclass
class DBLPSearchSource(JsonSchemaMixin):
    """SearchSource for DBLP"""

    __api_url = "https://dblp.org/search/publ/api?q="
    __api_url_venues = "https://dblp.org/search/venue/api?q="

    source_identifier = "{{dblp_key}}"
    search_type = colrev.settings.SearchType.DB
    __dblp_md_filename = Path("data/search/md_dblp.bib")

    @dataclass
    class DBLPSearchSourceSettings(colrev.settings.SearchSource, JsonSchemaMixin):
        """Settings for DBLPSearchSource"""

        # pylint: disable=duplicate-code
        # pylint: disable=too-many-instance-attributes
        endpoint: str
        filename: Path
        search_type: colrev.settings.SearchType
        source_identifier: str
        search_parameters: dict
        load_conversion_package_endpoint: dict
        comment: typing.Optional[str]

        _details = {
            "search_parameters": {
                "tooltip": "Currently supports a scope item "
                "with venue_key and journal_abbreviated fields."
            },
        }

    settings_class = DBLPSearchSourceSettings

    def __init__(
        self,
        *,
        source_operation: colrev.operation.Operation,
        settings: dict = None,
    ) -> None:

        if settings:
            # DBLP as a search_source
            self.search_source = from_dict(
                data_class=self.settings_class, data=settings
            )
        else:
            # DBLP as an md-prep source
            dblp_md_source_l = [
                s
                for s in source_operation.review_manager.settings.sources
                if s.filename == self.__dblp_md_filename
            ]
            if dblp_md_source_l:
                self.search_source = dblp_md_source_l[0]
            else:
                self.search_source = colrev.settings.SearchSource(
                    endpoint="colrev_built_in.dblp",
                    filename=self.__dblp_md_filename,
                    search_type=colrev.settings.SearchType.OTHER,
                    source_identifier=self.source_identifier,
                    search_parameters={},
                    load_conversion_package_endpoint={
                        "endpoint": "colrev_built_in.bibtex"
                    },
                    comment="",
                )
        self.dblp_lock = Lock()
        self.origin_prefix = self.search_source.get_origin_prefix()

    def check_availability(
        self, *, source_operation: colrev.operation.Operation
    ) -> None:
        """Check status (availability) of DBLP API"""

        try:
            # pylint: disable=duplicate-code
            test_rec = {
                "ENTRYTYPE": "article",
                "doi": "10.17705/1cais.04607",
                "author": "Schryen, Guido and Wagner, Gerit and Benlian, Alexander "
                "and Paré, Guy",
                "title": "A Knowledge Development Perspective on Literature Reviews: "
                "Validation of a new Typology in the IS Field",
                "ID": "SchryenEtAl2021",
                "journal": "Communications of the Association for Information Systems",
                "volume": "46",
                "year": "2020",
                "colrev_status": colrev.record.RecordState.md_prepared,  # type: ignore
            }

            query = "" + str(test_rec.get("title", "")).replace("-", "_")

            dblp_record = self.__retrieve_dblp_records(
                review_manager=source_operation.review_manager,
                query=query,
            )[0]

            if 0 != len(dblp_record.data):
                assert dblp_record.data["title"] == test_rec["title"]
                assert dblp_record.data["author"] == test_rec["author"]
            else:
                if not source_operation.force_mode:
                    raise colrev_exceptions.ServiceNotAvailableException("DBLP")
        except requests.exceptions.RequestException as exc:
            if not source_operation.force_mode:
                raise colrev_exceptions.ServiceNotAvailableException("DBLP") from exc

    def __get_dblp_venue(
        self,
        *,
        session: requests.Session,
        review_manager: colrev.review_manager.ReviewManager,
        timeout: int,
        venue_string: str,
        venue_type: str,
    ) -> str:
        # Note : venue_string should be like "behaviourIT"
        # Note : journals that have been renamed seem to return the latest
        # journal name. Example:
        # https://dblp.org/db/journals/jasis/index.html
        venue = venue_string
        url = self.__api_url_venues + venue_string.replace(" ", "+") + "&format=json"
        headers = {"user-agent": f"{__name__} (mailto:{review_manager.email})"}
        try:
            ret = session.request("GET", url, headers=headers, timeout=timeout)
            ret.raise_for_status()
            data = json.loads(ret.text)
            if "hit" not in data["result"]["hits"]:
                return ""
            hits = data["result"]["hits"]["hit"]
            for hit in hits:
                if hit["info"]["type"] != venue_type:
                    continue
                if f"/{venue_string.lower()}/" in hit["info"]["url"].lower():
                    venue = hit["info"]["venue"]
                    break

            venue = re.sub(r" \(.*?\)", "", venue)
        except requests.exceptions.RequestException:
            pass
        return venue

    def __dblp_json_to_dict(
        self,
        *,
        review_manager: colrev.review_manager.ReviewManager,
        session: requests.Session,
        item: dict,
        timeout: int,
    ) -> dict:
        # pylint: disable=too-many-branches

        # To test in browser:
        # https://dblp.org/search/publ/api?q=ADD_TITLE&format=json

        retrieved_record = {}
        if "Withdrawn Items" == item["type"]:
            if "journals" == item["key"][:8]:
                item["type"] = "Journal Articles"
            if "conf" == item["key"][:4]:
                item["type"] = "Conference and Workshop Papers"
            retrieved_record["warning"] = "Withdrawn (according to DBLP)"
        if "Journal Articles" == item["type"]:
            retrieved_record["ENTRYTYPE"] = "article"
            lpos = item["key"].find("/") + 1
            rpos = item["key"].rfind("/")
            ven_key = item["key"][lpos:rpos]
            retrieved_record["journal"] = self.__get_dblp_venue(
                session=session,
                review_manager=review_manager,
                timeout=timeout,
                venue_string=ven_key,
                venue_type="Journal",
            )
        if "Conference and Workshop Papers" == item["type"]:
            retrieved_record["ENTRYTYPE"] = "inproceedings"
            lpos = item["key"].find("/") + 1
            rpos = item["key"].rfind("/")
            ven_key = item["key"][lpos:rpos]
            retrieved_record["booktitle"] = self.__get_dblp_venue(
                session=session,
                review_manager=review_manager,
                venue_string=ven_key,
                venue_type="Conference or Workshop",
                timeout=timeout,
            )
        if "title" in item:
            retrieved_record["title"] = item["title"].rstrip(".").rstrip()
        if "year" in item:
            retrieved_record["year"] = item["year"]
        if "volume" in item:
            retrieved_record["volume"] = item["volume"]
        if "number" in item:
            retrieved_record["number"] = item["number"]
        if "pages" in item:
            retrieved_record["pages"] = item["pages"].replace("-", "--")
        if "authors" in item:
            if "author" in item["authors"]:
                if isinstance(item["authors"]["author"], dict):
                    author_string = item["authors"]["author"]["text"]
                else:
                    authors_nodes = [
                        author
                        for author in item["authors"]["author"]
                        if isinstance(author, dict)
                    ]
                    authors = [x["text"] for x in authors_nodes if "text" in x]
                    author_string = " and ".join(authors)
                author_string = colrev.record.PrepRecord.format_author_field(
                    input_string=author_string
                )
                retrieved_record["author"] = author_string

        if "key" in item:
            retrieved_record["dblp_key"] = "https://dblp.org/rec/" + item["key"]

        if "doi" in item:
            retrieved_record["doi"] = item["doi"].upper()
        if "ee" in item:
            if "https://doi.org" not in item["ee"]:
                retrieved_record["url"] = item["ee"]

        for key, value in retrieved_record.items():
            retrieved_record[key] = (
                html.unescape(value).replace("{", "").replace("}", "")
            )

        return retrieved_record

    def __retrieve_dblp_records(
        self,
        *,
        review_manager: colrev.review_manager.ReviewManager,
        query: str = None,
        url: str = None,
        timeout: int = 10,
    ) -> list:
        """Retrieve records from DBLP based on a query"""

        # https://dblp.org/search/publ/api?q=ADD_TITLE&format=json

        try:
            assert query is not None or url is not None
            session = review_manager.get_cached_session()
            items = []

            if query:
                query = re.sub(r"[\W]+", " ", query.replace(" ", "_"))
                url = self.__api_url + query.replace(" ", "+") + "&format=json"

            headers = {"user-agent": f"{__name__}  (mailto:{review_manager.email})"}
            # review_manager.logger.debug(url)
            ret = session.request(
                "GET", url, headers=headers, timeout=timeout  # type: ignore
            )
            ret.raise_for_status()
            if ret.status_code == 500:
                return []

            data = json.loads(ret.text)
            if "hits" not in data["result"]:
                return []
            if "hit" not in data["result"]["hits"]:
                return []
            hits = data["result"]["hits"]["hit"]
            items = [hit["info"] for hit in hits]
            dblp_dicts = [
                self.__dblp_json_to_dict(
                    review_manager=review_manager,
                    session=session,
                    item=item,
                    timeout=timeout,
                )
                for item in items
            ]
            retrieved_records = [
                colrev.record.PrepRecord(data=dblp_dict) for dblp_dict in dblp_dicts
            ]
            for retrieved_record in retrieved_records:
                # Note : DBLP provides number-of-pages (instead of pages start-end)
                if "pages" in retrieved_record.data:
                    del retrieved_record.data["pages"]
                retrieved_record.add_provenance_all(
                    source=retrieved_record.data["dblp_key"]
                )

        # pylint: disable=duplicate-code
        except OperationalError as exc:
            raise colrev_exceptions.ServiceNotAvailableException(
                "sqlite, required for requests CachedSession "
                "(possibly caused by concurrent operations)"
            ) from exc

        return retrieved_records

    def validate_source(
        self,
        search_operation: colrev.ops.search.Search,
        source: colrev.settings.SearchSource,
    ) -> None:
        """Validate the SearchSource (parameters etc.)"""

        search_operation.review_manager.logger.debug(
            f"Validate SearchSource {source.filename}"
        )

        if source.source_identifier != self.source_identifier:
            raise colrev_exceptions.InvalidQueryException(
                f"Invalid source_identifier: {source.source_identifier} "
                f"(should be {self.source_identifier})"
            )

        # maybe : validate/assert that the venue_key is available
        if "scope" in source.search_parameters:
            if "venue_key" not in source.search_parameters["scope"]:
                raise colrev_exceptions.InvalidQueryException(
                    "venue_key required in search_parameters/scope"
                )
            if "journal_abbreviated" not in source.search_parameters["scope"]:
                raise colrev_exceptions.InvalidQueryException(
                    "journal_abbreviated required in search_parameters/scope"
                )
        elif "query" in source.search_parameters:
            assert source.search_parameters["query"].startswith(
                "https://dblp.org/search/publ/api?q="
            )
        elif source.is_md_source():
            pass
            # assert params empty
        else:
            raise colrev_exceptions.InvalidQueryException(
                "scope or query required in search_parameters"
            )

        search_operation.review_manager.logger.debug(
            f"SearchSource {source.filename} validated"
        )

    def __run_md_search_update(
        self,
        *,
        search_operation: colrev.ops.search.Search,
        dblp_feed: connector_utils.GeneralOriginFeed,
    ) -> None:

        records = search_operation.review_manager.dataset.load_records_dict()

        nr_changed = 0

        for feed_record_dict in dblp_feed.feed_records.values():
            feed_record = colrev.record.Record(data=feed_record_dict)
            query = "" + feed_record.data.get("title", "").replace("-", "_")
            for retrieved_record in self.__retrieve_dblp_records(
                review_manager=search_operation.review_manager,
                query=query,
            ):
                if retrieved_record.data["dblp_key"] != feed_record.data["dblp_key"]:
                    continue

                dblp_feed.set_id(record_dict=retrieved_record.data)
                prev_record_dict_version = {}
                if retrieved_record.data["ID"] in dblp_feed.feed_records:
                    prev_record_dict_version = dblp_feed.feed_records[
                        retrieved_record.data["ID"]
                    ]

                dblp_feed.add_record(record=retrieved_record)
                # TODO:
                # if "Withdrawn (according to DBLP)" in record.data.get(
                #     "warning", ""
                # ):
                #     record.prescreen_exclude(reason="retracted")
                #     record.remove_field(key="warning")
                changed = search_operation.update_existing_record(
                    records=records,
                    record_dict=retrieved_record.data,
                    prev_record_dict_version=prev_record_dict_version,
                    source=self.search_source,
                )
                if changed:
                    nr_changed += 1

        if nr_changed > 0:
            search_operation.review_manager.logger.info(
                f"{colors.GREEN}Updated {nr_changed} "
                f"records based on DBLP{colors.END}"
            )
        else:
            search_operation.review_manager.logger.info(
                f"{colors.GREEN}Records up-to-date with DBLP{colors.END}"
            )

        dblp_feed.save_feed_file()
        search_operation.review_manager.dataset.save_records_dict(records=records)
        search_operation.review_manager.dataset.add_record_changes()

    def __run_parameter_search(
        self,
        *,
        search_operation: colrev.ops.search.Search,
        dblp_feed: connector_utils.GeneralOriginFeed,
    ) -> None:

        # pylint: disable=too-many-branches
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-nested-blocks
        # pylint: disable=too-many-statements

        records = search_operation.review_manager.dataset.load_records_dict()

        try:
            # Note : journal_abbreviated is the abbreviated venue_key

            __api_url = "https://dblp.org/search/publ/api?q="
            nr_retrieved, nr_added, nr_changed = 0, 0, 0
            start = 1980
            if (
                len(dblp_feed.feed_records) > 100
                and not search_operation.review_manager.force_mode
            ):
                start = datetime.now().year - 2

            for year in range(start, datetime.now().year):

                search_operation.review_manager.logger.debug(f"Retrieve year {year}")

                if "scope" in self.search_source.search_parameters:
                    query = (
                        __api_url
                        + self.search_source.search_parameters["scope"][
                            "journal_abbreviated"
                        ]
                        + "+"
                        + str(year)
                    )
                    # query = params['scope']["venue_key"] + "+" + str(year)
                elif "query" in self.search_source.search_parameters:
                    query = (
                        self.search_source.search_parameters["query"] + "+" + str(year)
                    )

                nr_retrieved = 0
                batch_size = 250
                while True:
                    url = (
                        query.replace(" ", "+")
                        + f"&format=json&h={batch_size}&f={nr_retrieved}"
                    )
                    nr_retrieved += batch_size
                    # search_operation.review_manager.logger.debug(url)

                    retrieved = False
                    for retrieved_record in self.__retrieve_dblp_records(
                        review_manager=search_operation.review_manager, url=url
                    ):
                        if "colrev_data_provenance" in retrieved_record.data:
                            del retrieved_record.data["colrev_data_provenance"]
                        if "colrev_masterdata_provenance" in retrieved_record.data:
                            del retrieved_record.data["colrev_masterdata_provenance"]

                        retrieved = True

                        if "scope" in self.search_source.search_parameters:
                            if (
                                f"{self.search_source.search_parameters['scope']['venue_key']}/"
                                not in retrieved_record.data["dblp_key"]
                            ):
                                continue
                        if retrieved_record.data.get("ENTRYTYPE", "") not in [
                            "article",
                            "inproceedings",
                        ]:
                            continue

                        dblp_feed.set_id(record_dict=retrieved_record.data)
                        prev_record_dict_version = {}
                        if retrieved_record.data["ID"] in dblp_feed.feed_records:
                            prev_record_dict_version = dblp_feed.feed_records[
                                retrieved_record.data["ID"]
                            ]

                        added = dblp_feed.add_record(
                            record=retrieved_record,
                        )
                        if added:
                            nr_added += 1

                        changed = search_operation.update_existing_record(
                            records=records,
                            record_dict=retrieved_record.data,
                            prev_record_dict_version=prev_record_dict_version,
                            source=self.search_source,
                        )
                        if changed:
                            nr_changed += 1

                    if not retrieved:
                        break

                dblp_feed.save_feed_file()

            if nr_retrieved > 0:
                search_operation.review_manager.logger.info(
                    f"{colors.GREEN}Retrieved {nr_added} new records{colors.END}"
                )
            else:
                search_operation.review_manager.logger.info(
                    f"{colors.GREEN}No additional records retrieved{colors.END}"
                )

            if nr_changed > 0:
                search_operation.review_manager.logger.info(
                    f"{colors.GREEN}Updated {nr_changed} "
                    f"records based on DBLP{colors.END}"
                )
            else:
                search_operation.review_manager.logger.info(
                    f"{colors.GREEN}Records up-to-date with DBLP{colors.END}"
                )

        except UnicodeEncodeError:
            print("UnicodeEncodeError - this needs to be fixed at some time")
        except (
            requests.exceptions.ReadTimeout,
            requests.exceptions.HTTPError,
            requests.exceptions.ConnectionError,
        ):
            pass

    def run_search(
        self, search_operation: colrev.ops.search.Search, update_only: bool
    ) -> None:
        """Run a search of DBLP"""

        search_operation.review_manager.logger.debug(
            f"Retrieve DBLP: {self.search_source.search_parameters}"
        )

        dblp_feed = connector_utils.GeneralOriginFeed(
            source_operation=search_operation,
            source=self.search_source,
            feed_file=self.search_source.filename,
            update_only=update_only,
            key="dblp_key",
        )

        if self.search_source.is_md_source():
            self.__run_md_search_update(
                search_operation=search_operation,
                dblp_feed=dblp_feed,
            )

        else:
            self.__run_parameter_search(
                search_operation=search_operation,
                dblp_feed=dblp_feed,
            )

    @classmethod
    def heuristic(cls, filename: Path, data: str) -> dict:
        """Source heuristic for DBLP"""

        result = {"confidence": 0.0}
        # Simple heuristic:
        if "bibsource = {dblp computer scienc" in data:
            result["confidence"] = 1.0
            return result
        return result

    def load_fixes(
        self,
        load_operation: colrev.ops.load.Load,
        source: colrev.settings.SearchSource,
        records: typing.Dict,
    ) -> dict:
        """Load fixes for DBLP"""

        return records

    def prepare(
        self, record: colrev.record.Record, source: colrev.settings.SearchSource
    ) -> colrev.record.Record:
        """Source-specific preparation for DBLP"""

        return record

    def get_masterdata_from_dblp(
        self, *, prep_operation: colrev.ops.prep.Prep, record: colrev.record.Record
    ) -> colrev.record.Record:
        """Retrieve masterdata from DBLP based on similarity with the record provided"""

        if any(self.origin_prefix in o for o in record.data["colrev_origin"]):
            # Already linked to a crossref record
            return record

        same_record_type_required = (
            prep_operation.review_manager.settings.is_curated_masterdata_repo()
        )

        try:
            query = "" + record.data.get("title", "").replace("-", "_")
            # Note: queries combining title+author/journal do not seem to work any more
            # if "author" in record:
            #     query = query + "_" + record["author"].split(",")[0]
            # if "booktitle" in record:
            #     query = query + "_" + record["booktitle"]
            # if "journal" in record:
            #     query = query + "_" + record["journal"]
            # if "year" in record:
            #     query = query + "_" + record["year"]

            for retrieved_record in self.__retrieve_dblp_records(
                review_manager=prep_operation.review_manager,
                query=query,
            ):
                similarity = colrev.record.PrepRecord.get_retrieval_similarity(
                    record_original=record,
                    retrieved_record_original=retrieved_record,
                    same_record_type_required=same_record_type_required,
                )
                if similarity > prep_operation.retrieval_similarity:
                    # prep_operation.review_manager.logger.debug("Found matching record")
                    # prep_operation.review_manager.logger.debug(
                    #     f"dblp similarity: {similarity} "
                    #     f"(>{prep_operation.retrieval_similarity})"
                    # )

                    self.dblp_lock.acquire(timeout=60)

                    # Note : need to reload file because the object is not shared between processes
                    dblp_feed = connector_utils.GeneralOriginFeed(
                        source_operation=prep_operation,
                        source=self.search_source,
                        feed_file=self.__dblp_md_filename,
                        update_only=False,
                        key="dblp_key",
                    )

                    dblp_feed.set_id(record_dict=retrieved_record.data)
                    dblp_feed.add_record(record=retrieved_record)

                    record.merge(
                        merging_record=retrieved_record,
                        default_source=retrieved_record.data["colrev_origin"][0],
                    )
                    record.set_masterdata_complete(
                        source_identifier=retrieved_record.data["colrev_origin"][0]
                    )
                    record.set_status(
                        target_state=colrev.record.RecordState.md_prepared
                    )
                    if "Withdrawn (according to DBLP)" in record.data.get(
                        "warning", ""
                    ):
                        record.prescreen_exclude(reason="retracted")
                        record.remove_field(key="warning")

                    dblp_feed.save_feed_file()
                    self.dblp_lock.release()
                    return record

        except (requests.exceptions.RequestException, UnicodeEncodeError):
            pass

        return record


if __name__ == "__main__":
    pass
