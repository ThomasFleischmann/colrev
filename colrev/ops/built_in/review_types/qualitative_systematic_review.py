#! /usr/bin/env python
"""Qualitative systematic review"""
from dataclasses import dataclass

import zope.interface
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.ops.search
import colrev.record
from colrev.ops.built_in.search_sources.open_citations_forward_search import (
    OpenCitationsSearchSource,
)
from colrev.ops.built_in.search_sources.pdf_backward_search import (
    BackwardSearchSource,
)

# pylint: disable=unused-argument
# pylint: disable=duplicate-code
# pylint: disable=too-few-public-methods


@zope.interface.implementer(
    colrev.env.package_manager.ReviewTypePackageEndpointInterface
)
@dataclass
class QualitativeSystematicReview(JsonSchemaMixin):
    """Qualitative systematic review"""

    settings_class = colrev.env.package_manager.DefaultSettings

    def __init__(
        self, *, operation: colrev.operation.CheckOperation, settings: dict
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)

    def __str__(self) -> str:
        return "qualitative systematic review"

    def initialize(
        self, settings: colrev.settings.Settings
    ) -> colrev.settings.Settings:
        """Initialize a qualitative systematic review"""

        settings.sources.append(OpenCitationsSearchSource.get_default_source())
        settings.sources.append(BackwardSearchSource.get_default_source())

        settings.data.data_package_endpoints = [
            {"endpoint": "colrev_built_in.prisma", "version": "1.0"},
            {
                "endpoint": "colrev_built_in.structured",
                "version": "1.0",
                "fields": [],
            },
            {
                "endpoint": "colrev_built_in.manuscript",
                "version": "1.0",
                "word_template": "APA-7.docx",
                "csl_style": "apa.csl",
            },
        ]
        return settings


if __name__ == "__main__":
    pass
