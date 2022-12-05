#! /usr/bin/env python
"""SearchSource: directory containing video files"""
from __future__ import annotations

import typing
from dataclasses import dataclass
from pathlib import Path

import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.built_in.search_sources.utils as connector_utils
import colrev.ops.built_in.search_sources.website as website_connector
import colrev.ops.search
import colrev.record
import colrev.ui_cli.cli_colors as colors

# pylint: disable=unused-argument
# pylint: disable=duplicate-code


@zope.interface.implementer(
    colrev.env.package_manager.SearchSourcePackageEndpointInterface
)
@dataclass
class VideoDirSearchSource(JsonSchemaMixin):
    """SearchSource for directory containing video files"""

    settings_class = colrev.env.package_manager.DefaultSourceSettings
    source_identifier = "{{file}}"
    search_type = colrev.settings.SearchType.OTHER

    def __init__(
        self, *, source_operation: colrev.operation.CheckOperation, settings: dict
    ) -> None:

        self.search_source = from_dict(data_class=self.settings_class, data=settings)
        self.source_operation = source_operation
        self.pdf_preparation_operation = (
            source_operation.review_manager.get_pdf_prep_operation(
                notify_state_transition_operation=False
            )
        )

        self.video_path = source_operation.review_manager.path / Path(
            self.search_source.search_parameters["scope"]["path"]
        )
        self.review_manager = source_operation.review_manager
        self.prep_operation = self.review_manager.get_prep_operation()

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

        if "path" not in source.search_parameters["scope"]:
            raise colrev_exceptions.InvalidQueryException(
                "path required in search_parameters/scope"
            )
        search_operation.review_manager.logger.debug(
            f"SearchSource {source.filename} validated"
        )

    def __index_video(self, *, path: Path) -> dict:
        record_dict = {"ENTRYTYPE": "online", "file": path}
        # TODO : extract based on metadata
        return record_dict

    def run_search(
        self, search_operation: colrev.ops.search.Search, update_only: bool
    ) -> None:
        """Run a search of a directory containing videos"""

        search_operation.review_manager.logger.info(
            f"{colors.ORANGE}For better metadata, please add the url "
            f"(or authors and title){colors.END}"
        )

        video_feed = connector_utils.GeneralOriginFeed(
            source_operation=search_operation,
            source=self.search_source,
            feed_file=self.search_source.filename,
            update_only=False,
            key="file",
        )

        overall_files = [
            x.relative_to(search_operation.review_manager.path)
            for x in self.video_path.glob("**/*.mp4")
        ]

        new_records_added = 0
        for file_to_add in overall_files:

            new_record = self.__index_video(path=file_to_add)

            video_feed.set_id(record_dict=new_record)
            added = video_feed.add_record(
                record=colrev.record.Record(data=new_record),
            )
            if added:
                new_records_added += 1

        video_feed.save_feed_file()

        search_operation.review_manager.logger.info(
            f"New videos added: {new_records_added}"
        )

    @classmethod
    def heuristic(cls, filename: Path, data: str) -> dict:
        """Source heuristic for video directories"""

        result = {"confidence": 0.0}

        return result

    def load_fixes(
        self,
        load_operation: colrev.ops.load.Load,
        source: colrev.settings.SearchSource,
        records: typing.Dict,
    ) -> dict:
        """Load fixes for video directories"""

        return records

    def prepare(
        self, record: colrev.record.Record, source: colrev.settings.SearchSource
    ) -> colrev.record.Record:
        """Source-specific preparation for video directories"""

        if "url" in record.data:
            url_connector = website_connector.WebsiteConnector()
            url_record = record.copy_prep_rec()
            url_connector.retrieve_md_from_website(
                record=url_record, prep_operation=self.prep_operation
            )
            if url_record.data.get("author", "") != "":
                record.update_field(
                    key="author", value=url_record.data["author"], source="website"
                )
            if url_record.data.get("title", "") != "":
                record.update_field(
                    key="title", value=url_record.data["title"], source="website"
                )

        return record


if __name__ == "__main__":
    pass
