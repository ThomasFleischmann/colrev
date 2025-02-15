#!/usr/bin/env python
"""Tests of the CoLRev pdf-prep operations"""
import colrev.review_manager


def test_pdf_prep(  # type: ignore
    base_repo_review_manager: colrev.review_manager.ReviewManager, helpers
) -> None:
    """Test the pdf-prep operation"""

    helpers.reset_commit(
        review_manager=base_repo_review_manager, commit="pdf_get_commit"
    )
    # pdf_prep_operation = base_repo_review_manager.get_pdf_prep_operation(reprocess=False)
    # pdf_prep_operation.main()


def test_pdf_discard(  # type: ignore
    base_repo_review_manager: colrev.review_manager.ReviewManager, helpers
) -> None:
    """Test the pdfs --discard"""

    helpers.reset_commit(
        review_manager=base_repo_review_manager, commit="pdf_prep_commit"
    )
    pdf_get_man_operation = base_repo_review_manager.get_pdf_get_man_operation()
    pdf_get_man_operation.discard()
