from pathlib import Path

import pytest

from paperflow import pipeline
from paperflow.pipeline import (
    PaperResult,
    UnsupportedRouteError,
    process_doi,
)


def _result(
    *,
    doi: str,
    route: str,
    tmp_path: Path,
) -> PaperResult:
    qa_path = tmp_path / "qa.json"

    return PaperResult(
        doi=doi,
        route=route,
        source="test",
        status="success",
        raw_markdown_path=None,
        llm_markdown_path=None,
        qa_path=qa_path,
        fallback_used=False,
    )


def test_process_doi_dispatches_elsevier(
    tmp_path,
    monkeypatch,
):
    expected = _result(
        doi=("10.1016/j.enbuild.2025.115908"),
        route="elsevier",
        tmp_path=tmp_path,
    )

    def fake_process(
        paths,
        settings,
    ):
        assert paths.doi == expected.doi

        return expected

    monkeypatch.setattr(
        pipeline,
        "_process_elsevier",
        fake_process,
    )

    result = process_doi(
        expected.doi,
        library_root=tmp_path,
        settings=object(),
    )

    assert result is expected


def test_process_doi_dispatches_nature(
    tmp_path,
    monkeypatch,
):
    doi = "10.1038/s41467-019-11026-x"

    expected = _result(
        doi=doi,
        route="nature",
        tmp_path=tmp_path,
    )

    def fake_process(
        paths,
        settings,
        *,
        pdf_path=None,
    ):
        assert paths.doi == doi
        assert pdf_path is None

        return expected

    monkeypatch.setattr(
        pipeline,
        "_process_nature",
        fake_process,
    )

    result = process_doi(
        doi,
        library_root=tmp_path,
        settings=object(),
    )

    assert result == expected


def test_process_doi_dispatches_building_simulation(
    tmp_path,
    monkeypatch,
):
    doi = "10.1007/s12273-024-1206-6"

    source_pdf = tmp_path / "source.pdf"

    source_pdf.write_bytes(b"fake")

    expected = _result(
        doi=doi,
        route=("building_simulation"),
        tmp_path=tmp_path,
    )

    def fake_process(
        paths,
        settings,
        *,
        pdf_path,
    ):
        assert paths.doi == doi

        assert Path(pdf_path) == source_pdf

        return expected

    monkeypatch.setattr(
        pipeline,
        "_process_building_simulation",
        fake_process,
    )

    result = process_doi(
        doi,
        pdf_path=source_pdf,
        library_root=tmp_path,
        settings=object(),
    )

    assert result is expected

def test_building_simulation_uses_local_directory_pdf(
    tmp_path,
    monkeypatch,
):
    doi = "10.1007/s12273-024-1206-6"

    paper_directory = (
        tmp_path
        / "10.1007_s12273-024-1206-6"
    )

    paper_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    local_pdf = (
        paper_directory
        / "downloaded article.pdf"
    )

    local_pdf.write_bytes(
        b"%PDF-1.7\n"
    )

    paths = type(
        "Paths",
        (),
        {
            "doi": doi,
            "directory": paper_directory,
        },
    )()

    expected = _result(
        doi=doi,
        route="building_simulation",
        tmp_path=tmp_path,
    )

    captured = {}

    def fake_process_pdf_with_mineru(
        paths,
        settings,
        *,
        pdf_content,
        route,
        source,
        fallback_used,
        fallback_reason,
        source_url,
        source_file,
    ):
        captured["pdf_content"] = (
            pdf_content
        )

        captured["route"] = route
        captured["source"] = source
        captured["fallback_used"] = (
            fallback_used
        )

        captured["source_file"] = (
            source_file
        )

        return expected

    monkeypatch.setattr(
        pipeline,
        "_process_pdf_with_mineru",
        fake_process_pdf_with_mineru,
    )

    result = (
        pipeline
        ._process_building_simulation(
            paths,
            object(),
            pdf_path=None,
        )
    )

    assert result == expected

    assert (
        captured["pdf_content"]
        is None
    )

    assert (
        captured["route"]
        is pipeline.Route.BUILDING_SIMULATION
    )

    assert (
        captured["source"]
        == "local_pdf_mineru"
    )

    assert (
        captured["fallback_used"]
        is False
    )

    assert (
        Path(
            captured["source_file"]
        )
        == local_pdf
    )


def test_process_doi_rejects_unsupported_route(
    tmp_path,
):
    with pytest.raises(UnsupportedRouteError):
        process_doi(
            "10.5555/example",
            library_root=tmp_path,
            settings=object(),
        )
