#! /usr/bin/env python
"""Consolidation of metadata based on DBLP API as a prep operation"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import timeout_decorator
import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.ops.built_in.search_sources.dblp as dblp_connector
import colrev.ops.search_sources
import colrev.record

if TYPE_CHECKING:
    import colrev.ops.prep

# pylint: disable=too-few-public-methods
# pylint: disable=duplicate-code


@zope.interface.implementer(colrev.env.package_manager.PrepPackageEndpointInterface)
@dataclass
class DBLPMetadataPrep(JsonSchemaMixin):
    """Prepares records based on dblp.org metadata"""

    settings_class = colrev.env.package_manager.DefaultSettings

    source_correction_hint = (
        "send and email to dblp@dagstuhl.de"
        + " (see https://dblp.org/faq/How+can+I+correct+errors+in+dblp.html)"
    )
    always_apply_changes = False

    def __init__(
        self,
        *,
        prep_operation: colrev.ops.prep.Prep,  # pylint: disable=unused-argument
        settings: dict,
    ) -> None:
        self.settings = from_dict(data_class=self.settings_class, data=settings)
        self.dblp_source = dblp_connector.DBLPSearchSource(
            source_operation=prep_operation
        )

    def check_availability(
        self, *, source_operation: colrev.operation.Operation
    ) -> None:
        """Check status (availability) of the Crossref API"""
        self.dblp_source.check_availability(source_operation=source_operation)

    @timeout_decorator.timeout(60, use_signals=False)
    def prepare(
        self, prep_operation: colrev.ops.prep.Prep, record: colrev.record.PrepRecord
    ) -> colrev.record.Record:
        """Prepare a record by retrieving its metadata from DBLP"""

        self.dblp_source.get_masterdata_from_dblp(
            prep_operation=prep_operation, record=record
        )

        return record


if __name__ == "__main__":
    pass
