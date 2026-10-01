import csv
from pathlib import Path

from paperflow import batch
from paperflow.pipeline import (
    PaperResult,
    PipelineContentError,
)


def _paper_result(
    tmp_path: Path,
    *,
    doi: str,
    route: str,
    source: str,
    status: str = "success",
    fallback_used: bool = False,
) -> PaperResult:
    return PaperResult(
        doi=doi,
        route=route,
        source=source,
        status=status,
        raw_markdown_path=None,
        llm_markdown_path=(tmp_path / "paper_llm.md"),
        qa_path=(tmp_path / "qa.json"),
        fallback_used=fallback_used,
    )


def test_load_dois_ignores_blank_comments_and_duplicates(
    tmp_path,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        (
            "# Elsevier\n"
            "\n"
            "10.1016/j.enbuild.2025.115908\n"
            "  10.1038/s41467-026-78118-3  \n"
            "\n"
            "# duplicate\n"
            "10.1016/j.enbuild.2025.115908\n"
        ),
        encoding="utf-8",
    )

    result = batch.load_dois(input_path)

    assert result == [
        "10.1016/j.enbuild.2025.115908",
        "10.1038/s41467-026-78118-3",
    ]


def test_load_dois_supports_utf8_bom(
    tmp_path,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        ("10.1016/j.enbuild.2025.115908\n10.1038/s41467-026-78118-3\n"),
        encoding="utf-8-sig",
    )

    result = batch.load_dois(input_path)

    assert result == [
        "10.1016/j.enbuild.2025.115908",
        "10.1038/s41467-026-78118-3",
    ]


def test_load_dois_rejects_empty_file(
    tmp_path,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        ("\n# comment only\n\n"),
        encoding="utf-8",
    )

    try:
        batch.load_dois(input_path)
    except ValueError as exc:
        assert "No DOI entries" in str(exc)
    else:
        raise AssertionError("Expected ValueError.")


def test_run_batch_continues_after_known_failure(
    tmp_path,
    monkeypatch,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        ("10.1016/j.enbuild.2025.115908\n10.1038/s41467-026-78118-3\n10.1007/s12273-026-1484-2\n"),
        encoding="utf-8",
    )

    library_root = tmp_path / "library"

    results_path = tmp_path / "batch_results.csv"

    calls: list[str] = []

    def fake_process_doi(
        doi,
        *,
        library_root,
    ):
        calls.append(doi)

        if doi.startswith("10.1038/"):
            raise PipelineContentError("test failure")

        if doi.startswith("10.1007/"):
            return _paper_result(
                tmp_path,
                doi=doi,
                route=("building_simulation"),
                source=("building_simulation_pdf_mineru"),
                status="warning",
            )

        return _paper_result(
            tmp_path,
            doi=doi,
            route="elsevier",
            source="elsevier_xml",
        )

    monkeypatch.setattr(
        batch,
        "process_doi",
        fake_process_doi,
    )

    progress = []

    def on_result(
        item,
        total,
    ):
        progress.append(
            (
                item.index,
                total,
                item.status,
            )
        )

    result = batch.run_batch(
        input_path,
        library_root=library_root,
        results_path=results_path,
        on_result=on_result,
    )

    assert calls == [
        "10.1016/j.enbuild.2025.115908",
        "10.1038/s41467-026-78118-3",
        "10.1007/s12273-026-1484-2",
    ]

    assert result.total == 3

    assert result.success_count == 1

    assert result.warning_count == 1

    assert result.failed_count == 1

    assert progress == [
        (
            1,
            3,
            "success",
        ),
        (
            2,
            3,
            "failed",
        ),
        (
            3,
            3,
            "warning",
        ),
    ]

    assert results_path.is_file()

    with results_path.open(
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 3

    assert rows[0]["status"] == "success"

    assert rows[0]["fallback_used"] == "false"

    assert rows[1]["status"] == "failed"

    assert "PipelineContentError: test failure" in rows[1]["error"]

    assert rows[2]["status"] == "warning"


def test_run_batch_uses_default_results_path(
    tmp_path,
    monkeypatch,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        ("10.1016/j.enbuild.2025.115908\n"),
        encoding="utf-8",
    )

    library_root = tmp_path / "output"

    def fake_process_doi(
        doi,
        *,
        library_root,
    ):
        return _paper_result(
            tmp_path,
            doi=doi,
            route="elsevier",
            source="elsevier_xml",
        )

    monkeypatch.setattr(
        batch,
        "process_doi",
        fake_process_doi,
    )

    result = batch.run_batch(
        input_path,
        library_root=library_root,
    )

    assert result.results_path == library_root / "batch_results.csv"

    assert result.results_path.is_file()


def test_run_batch_preserves_fallback_flag(
    tmp_path,
    monkeypatch,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        ("10.1038/s41467-026-78118-3\n"),
        encoding="utf-8",
    )

    library_root = tmp_path / "library"

    monkeypatch.setattr(
        batch,
        "process_doi",
        lambda doi, *, library_root: _paper_result(
            tmp_path,
            doi=doi,
            route="nature",
            source=("nature_pdf_mineru"),
            status="warning",
            fallback_used=True,
        ),
    )

    result = batch.run_batch(
        input_path,
        library_root=library_root,
    )

    assert result.total == 1
    assert result.items[0].fallback_used is True

    with result.results_path.open(
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["fallback_used"] == "true"
