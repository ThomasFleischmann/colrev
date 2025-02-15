#!/usr/bin/env python
"""Test the local_index"""
from pathlib import Path

import pytest

import colrev.env.local_index
import colrev.env.tei_parser
import colrev.review_manager

# pylint: disable=line-too-long


def test_is_duplicate(local_index, local_index_test_records_dict) -> None:  # type: ignore
    """Test is_duplicate()"""
    record1_colrev_id = colrev.record.Record(
        data=local_index_test_records_dict[Path("misq.bib")]["AbbasZhouDengEtAl2018"]
    ).get_colrev_id()
    record2_colrev_id = colrev.record.Record(
        data=local_index_test_records_dict[Path("misq.bib")][
            "AbbasiAlbrechtVanceEtAl2012"
        ]
    ).get_colrev_id()
    expected = "no"
    actual = local_index.is_duplicate(
        record1_colrev_id=record1_colrev_id, record2_colrev_id=record2_colrev_id
    )
    assert expected == actual

    expected = "yes"
    actual = local_index.is_duplicate(
        record1_colrev_id=record1_colrev_id, record2_colrev_id=record1_colrev_id
    )
    assert expected == actual

    expected = "unknown"
    actual = local_index.is_duplicate(
        record1_colrev_id=record1_colrev_id,
        record2_colrev_id=["colrev_id1:|a|mis-quarterly|45|1|2020|rai|editorial"],
    )
    assert expected == actual


def test_get_year_from_toc(local_index) -> None:  # type: ignore
    """Test get_year_from_toc()"""

    with pytest.raises(
        colrev.exceptions.TOCNotAvailableException,
    ):
        record_dict = {"ENTRYTYPE": "article", "volume": "42", "number": "2"}
        local_index.get_year_from_toc(record_dict=record_dict)

    record_dict = {
        "ENTRYTYPE": "article",
        "journal": "MIS Quarterly",
        "volume": "42",
        "number": "2",
    }
    expected = "2018"
    actual = local_index.get_year_from_toc(record_dict=record_dict)
    assert expected == actual


def test_search(local_index) -> None:  # type: ignore
    """Test search()"""

    expected = [
        colrev.record.Record(
            data={
                "ENTRYTYPE": "article",
                "ID": "AbbasZhouDengEtAl2018",
                "author": "Abbas, Ahmed and Zhou, Yilu and Deng, Shasha and Zhang, Pengzhu",
                "colrev_data_provenance": {
                    "doi": {"note": "", "source": "pdfs.bib/0000000089"},
                    "url": {"note": "", "source": "DBLP.bib/001187"},
                },
                "colrev_masterdata_provenance": {
                    "CURATED": {"note": "", "source": "gh..."}
                },
                "colrev_status": colrev.record.RecordState.md_prepared,
                "curation_ID": "gh...#AbbasZhouDengEtAl2018",
                "doi": "10.25300/MISQ/2018/13239",
                "journal": "MIS Quarterly",
                "language": "eng",
                "number": "2",
                "pages": "427--464",
                "title": "Text Analytics to Support Sense-Making in Social Media: A Language-Action Perspective",
                "url": "https://misq.umn.edu/skin/frontend/default/misq/pdf/appendices/2018/V42I2Appendices/04_13239_RA_AbbasiZhou.pdf",
                "volume": "42",
                "year": "2018",
            }
        )
    ]
    actual = local_index.search(query="title LIKE '%social media%'")
    assert expected == actual

    expected = [
        colrev.record.Record(
            data={
                "ENTRYTYPE": "article",
                "ID": "AlaviLeidner2001",
                "author": "Alavi, Maryam and Leidner, Dorothy E.",
                "colrev_data_provenance": {
                    "doi": {"note": "", "source": "CROSSREF.bib/000516"},
                    "url": {"note": "", "source": "DBLP.bib/000528"},
                },
                "colrev_masterdata_provenance": {
                    "CURATED": {"note": "", "source": "gh..."}
                },
                "colrev_status": colrev.record.RecordState.md_prepared,
                "curation_ID": "gh...#AlaviLeidner2001",
                "doi": "10.2307/3250961",
                "journal": "MIS Quarterly",
                # TODO : should expect literature_review = True (layered field?!)
                "language": "eng",
                "number": "1",
                "title": "Review: Knowledge Management and Knowledge Management Systems: Conceptual Foundations and Research Issues",
                "url": "https://www.doi.org/10.2307/3250961",
                "volume": "25",
                "year": "2001",
            }
        )
    ]
    actual = local_index.search(
        query="title LIKE '%Knowledge Management and Knowledge Management Systems%'"
    )
    assert expected == actual


def test_get_fields_to_remove(local_index) -> None:  # type: ignore
    """Test get_fields_to_remove()"""

    record_dict = {
        "ENTRYTYPE": "article",
        "journal": "Communications of the Association for Information Systems",
        "year": "2021",
        "volume": "48",
        "number": "2",
    }
    expected = ["number"]
    actual = local_index.get_fields_to_remove(record_dict=record_dict)
    assert expected == actual

    record_dict = {
        "ENTRYTYPE": "inproceedings",
        "booktitle": "Communications of the Association for Information Systems",
        "year": "2021",
        "volume": "48",
        "number": "2",
    }
    expected = []
    actual = local_index.get_fields_to_remove(record_dict=record_dict)
    assert expected == actual


def test_retrieve_from_toc(local_index) -> None:  # type: ignore
    """Test retrieve_from_toc()"""

    record_dict = {
        "ENTRYTYPE": "article",
        "ID": "AbbasZhouDengEtAl2018",
        "author": "Abbas, Ahmed and Zhou, Yilu and Deng, Shasha and Zhang, Pengzhu",
        "journal": "MIS Quarterly",
        "language": "eng",
        "number": "2",
        "pages": "427-64",
        "curation_ID": "gh...#AbbasZhouDengEtAl2018",
        "title": "Text Analytics to Support Sense-Making in Social Media: A Language Perspective",
        "volume": "42",
        "year": "2018",
    }
    expected = {
        "ID": "AbbasZhouDengEtAl2018",
        "ENTRYTYPE": "article",
        "colrev_status": colrev.record.RecordState.md_prepared,
        "colrev_masterdata_provenance": {"CURATED": {"source": "gh...", "note": ""}},
        "colrev_data_provenance": {
            "doi": {"source": "pdfs.bib/0000000089", "note": ""},
            "url": {"source": "DBLP.bib/001187", "note": ""},
        },
        "doi": "10.25300/MISQ/2018/13239",
        "journal": "MIS Quarterly",
        "title": "Text Analytics to Support Sense-Making in Social Media: A Language-Action Perspective",
        "year": "2018",
        "volume": "42",
        "number": "2",
        "pages": "427--464",
        "url": "https://misq.umn.edu/skin/frontend/default/misq/pdf/appendices/2018/V42I2Appendices/04_13239_RA_AbbasiZhou.pdf",
        "language": "eng",
        "author": "Abbas, Ahmed and Zhou, Yilu and Deng, Shasha and Zhang, Pengzhu",
        "curation_ID": "gh...#AbbasZhouDengEtAl2018",
    }
    actual = local_index.retrieve_from_toc(
        record_dict=record_dict, similarity_threshold=0.8
    )
    assert expected == actual


def test_retrieve_based_on_colrev_pdf_id(local_index) -> None:  # type: ignore
    """Test retrieve_based_on_colrev_pdf_id()"""

    colrev_pdf_id = "cpid2:fffffffffcffffffe007ffffc0020003e0f20007fffffffff000000fff8001fffffc3fffffe007ffffc003fffe00007ffffffffff800001ff800001ff80003fff920725ff800001ff800001ff800001ff84041fff81fffffffffffffe000afffe0018007efff8007e2bd8007efff8007e00fffffffffffffffffffffffffffff"
    expected = {
        "ID": "AbbasiAlbrechtVanceEtAl2012",
        "ENTRYTYPE": "article",
        "colrev_status": colrev.record.RecordState.md_prepared,
        "colrev_masterdata_provenance": {"CURATED": {"source": "gh...", "note": ""}},
        "colrev_data_provenance": {
            "colrev_pdf_id": {"source": "file|pdf_hash", "note": ""},
            "file": {"source": "pdfs.bib/0000001378", "note": ""},
            "dblp_key": {"source": "DBLP.bib/000869", "note": ""},
            "url": {"source": "DBLP.bib/000869", "note": ""},
        },
        "colrev_pdf_id": "cpid2:fffffffffcffffffe007ffffc0020003e0f20007fffffffff000000fff8001fffffc3fffffe007ffffc003fffe00007ffffffffff800001ff800001ff80003fff920725ff800001ff800001ff800001ff84041fff81fffffffffffffe000afffe0018007efff8007e2bd8007efff8007e00fffffffffffffffffffffffffffff",
        "dblp_key": "https://dblp.org/rec/journals/misq/AbbasiAVH12",
        "journal": "MIS Quarterly",
        "title": "MetaFraud - A Meta-Learning Framework for Detecting Financial Fraud",
        "year": "2012",
        "volume": "36",
        "number": "4",
        "url": "http://misq.org/metafraud-a-meta-learning-framework-for-detecting-financial-fraud.html",
        "language": "eng",
        "author": "Abbasi, Ahmed and Albrecht, Conan and Vance, Anthony and Hansen, James",
        "curation_ID": "gh...#AbbasiAlbrechtVanceEtAl2012",
    }
    actual = local_index.retrieve_based_on_colrev_pdf_id(colrev_pdf_id=colrev_pdf_id)
    assert expected == actual


# next tests: index_tei:
# we could leave the file field for WagnerLukyanenkoParEtAl2022
# but if the PDF does not exist, the field is removed
# del record_dict["file"]
# and the index_tei immediately returns.

# def method(): # pragma: no cover
