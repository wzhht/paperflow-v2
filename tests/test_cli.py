from pathlib import Path

from typer.testing import CliRunner

from paperflow import cli
from paperflow.batch import (
    BatchItemResult,
    BatchRunResult,
)
from paperflow.pipeline import (
    PaperResult,
    PipelineContentError,
)

runner = CliRunner()


def _result(
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


def test_version(
    monkeypatch,
):
    monkeypatch.setattr(
        cli,
        "_get_version",
        lambda: "0.2.0",
    )

    result = runner.invoke(
        cli.app,
        [
            "version",
        ],
    )

    assert result.exit_code == 0

    assert "PaperFlow 0.2.0" in result.stdout


def test_process_nature(
    tmp_path,
    monkeypatch,
):
    doi = "10.1038/s41467-019-11026-x"

    expected = _result(
        tmp_path,
        doi=doi,
        route="nature",
        source=("springer_nature_jats"),
    )

    def fake_process_doi(
        requested_doi,
        *,
        pdf_path,
        library_root,
    ):
        assert requested_doi == doi
        assert pdf_path is None

        assert library_root == Path("workspace/library")

        return expected

    monkeypatch.setattr(
        cli,
        "process_doi",
        fake_process_doi,
    )

    result = runner.invoke(
        cli.app,
        [
            "process",
            doi,
        ],
    )

    assert result.exit_code == 0

    assert f"DOI = {doi}" in result.stdout

    assert "Route = nature" in result.stdout

    assert "Source = springer_nature_jats" in result.stdout

    assert "Status = success" in result.stdout

    assert "Fallback used = no" in result.stdout


def test_process_nature_pdf_fallback(
    tmp_path,
    monkeypatch,
):
    doi = "10.1038/s41467-026-78118-3"

    expected = _result(
        tmp_path,
        doi=doi,
        route="nature",
        source=("nature_pdf_mineru"),
        status="warning",
        fallback_used=True,
    )

    monkeypatch.setattr(
        cli,
        "process_doi",
        lambda *args, **kwargs: expected,
    )

    result = runner.invoke(
        cli.app,
        [
            "process",
            doi,
        ],
    )

    assert result.exit_code == 0

    assert "Source = nature_pdf_mineru" in result.stdout

    assert "Status = warning" in result.stdout

    assert "Fallback used = yes" in result.stdout


def test_process_building_simulation_with_pdf(
    tmp_path,
    monkeypatch,
):
    doi = "10.1007/s12273-024-1206-6"

    pdf = tmp_path / "paper.pdf"

    pdf.write_bytes(b"%PDF-1.7\n")

    expected = _result(
        tmp_path,
        doi=doi,
        route=("building_simulation"),
        source=("local_pdf_mineru"),
        status="warning",
    )

    captured = {}

    def fake_process_doi(
        requested_doi,
        *,
        pdf_path,
        library_root,
    ):
        captured["doi"] = requested_doi

        captured["pdf"] = pdf_path

        captured["library_root"] = library_root

        return expected

    monkeypatch.setattr(
        cli,
        "process_doi",
        fake_process_doi,
    )

    result = runner.invoke(
        cli.app,
        [
            "process",
            doi,
            "--pdf",
            str(pdf),
        ],
    )

    assert result.exit_code == 0

    assert captured["doi"] == doi

    assert Path(captured["pdf"]).resolve() == pdf.resolve()

    assert "Route = building_simulation" in result.stdout


def test_process_building_simulation_online(
    tmp_path,
    monkeypatch,
):
    doi = "10.1007/s12273-026-1484-2"

    expected = _result(
        tmp_path,
        doi=doi,
        route=("building_simulation"),
        source=("building_simulation_pdf_mineru"),
        status="warning",
    )

    def fake_process_doi(
        requested_doi,
        *,
        pdf_path,
        library_root,
    ):
        assert requested_doi == doi
        assert pdf_path is None

        return expected

    monkeypatch.setattr(
        cli,
        "process_doi",
        fake_process_doi,
    )

    result = runner.invoke(
        cli.app,
        [
            "process",
            doi,
        ],
    )

    assert result.exit_code == 0

    assert "Source = building_simulation_pdf_mineru" in result.stdout

    assert "Status = warning" in result.stdout


def test_process_reports_pipeline_error(
    monkeypatch,
):
    def fail(
        *args,
        **kwargs,
    ):
        raise PipelineContentError("test failure")

    monkeypatch.setattr(
        cli,
        "process_doi",
        fail,
    )

    result = runner.invoke(
        cli.app,
        [
            "process",
            ("10.1038/s41467-026-78118-3"),
        ],
    )

    assert result.exit_code == 1

    combined = result.stdout + (result.stderr if result.stderr else "")

    assert "PipelineContentError" in combined

    assert "test failure" in combined


def test_process_rejects_missing_pdf_path():
    result = runner.invoke(
        cli.app,
        [
            "process",
            ("10.1007/s12273-024-1206-6"),
            "--pdf",
            ("definitely-missing.pdf"),
        ],
    )

    assert result.exit_code != 0


def test_process_list(
    tmp_path,
    monkeypatch,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        ("10.1038/s41467-026-78118-3\n"),
        encoding="utf-8",
    )

    library_root = tmp_path / "output"

    def fake_run_batch(
        requested_input,
        *,
        library_root,
        results_path,
        on_result,
    ):
        item = BatchItemResult(
            index=1,
            doi=("10.1038/s41467-026-78118-3"),
            route="nature",
            source=("nature_pdf_mineru"),
            status="warning",
            fallback_used=True,
            llm_markdown=("paper_llm.md"),
            qa="qa.json",
            error="",
        )

        if on_result is not None:
            on_result(
                item,
                1,
            )

        resolved_results_path = (
            Path(results_path)
            if results_path is not None
            else (Path(library_root) / "batch_results.csv")
        )

        return BatchRunResult(
            input_path=Path(requested_input),
            library_root=Path(library_root),
            results_path=(resolved_results_path),
            total=1,
            success_count=0,
            warning_count=1,
            failed_count=0,
            items=(item,),
        )

    monkeypatch.setattr(
        cli,
        "run_batch",
        fake_run_batch,
    )

    result = runner.invoke(
        cli.app,
        [
            "process-list",
            str(input_path),
            "--library-root",
            str(library_root),
        ],
    )

    assert result.exit_code == 0

    assert "[1/1] 10.1038/s41467-026-78118-3" in result.stdout

    assert "nature_pdf_mineru" in result.stdout

    assert "Batch complete" in result.stdout

    assert "Total = 1" in result.stdout

    assert "Success = 0" in result.stdout

    assert "Warning = 1" in result.stdout

    assert "Failed = 0" in result.stdout


def test_process_list_custom_results_path(
    tmp_path,
    monkeypatch,
):
    input_path = tmp_path / "dois.txt"

    input_path.write_text(
        ("10.1016/j.enbuild.2025.115908\n"),
        encoding="utf-8",
    )

    library_root = tmp_path / "library"

    custom_results = tmp_path / "manifests" / "results.csv"

    captured = {}

    def fake_run_batch(
        requested_input,
        *,
        library_root,
        results_path,
        on_result,
    ):
        captured["results_path"] = results_path

        return BatchRunResult(
            input_path=Path(requested_input),
            library_root=Path(library_root),
            results_path=Path(results_path),
            total=1,
            success_count=1,
            warning_count=0,
            failed_count=0,
            items=(),
        )

    monkeypatch.setattr(
        cli,
        "run_batch",
        fake_run_batch,
    )

    result = runner.invoke(
        cli.app,
        [
            "process-list",
            str(input_path),
            "--library-root",
            str(library_root),
            "--results",
            str(custom_results),
        ],
    )

    assert result.exit_code == 0

    assert Path(captured["results_path"]) == custom_results

    assert str(custom_results) in result.stdout
