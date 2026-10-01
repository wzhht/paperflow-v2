import json

import pytest

from paperflow import recovery
from paperflow.recovery import (
    MultipleLocalPdfError,
    SpringerMetadataRecoveryError,
    find_local_pdf,
    write_restricted_access_artifacts,
)


def test_find_local_pdf_none(
    tmp_path,
):
    assert find_local_pdf(tmp_path) is None


def test_find_local_pdf_one(
    tmp_path,
):
    pdf = tmp_path / "whatever name.pdf"

    pdf.write_bytes(b"%PDF-1.7\n")

    result = find_local_pdf(tmp_path)

    assert result == pdf


def test_find_local_pdf_case_insensitive_extension(
    tmp_path,
):
    pdf = tmp_path / "ARTICLE.PDF"

    pdf.write_bytes(b"%PDF-1.7\n")

    result = find_local_pdf(tmp_path)

    assert result == pdf


def test_find_local_pdf_multiple_requires_explicit_selection(
    tmp_path,
):
    first = tmp_path / "article.pdf"

    second = tmp_path / "supplement.pdf"

    first.write_bytes(b"%PDF-1.7\n")

    second.write_bytes(b"%PDF-1.7\n")

    with pytest.raises(MultipleLocalPdfError):
        find_local_pdf(tmp_path)


def test_explicit_pdf_wins_with_multiple_files(
    tmp_path,
):
    first = tmp_path / "article.pdf"

    second = tmp_path / "supplement.pdf"

    first.write_bytes(b"%PDF-1.7\n")

    second.write_bytes(b"%PDF-1.7\n")

    result = find_local_pdf(
        tmp_path,
        explicit_pdf=first,
    )

    assert result == first


def test_select_exact_meta_record():
    payload = {
        "records": [
            {
                "doi": ("10.1038/s00000-000-00000-0"),
                "title": "Wrong article",
            },
            {
                "identifier": ("doi:10.1038/s41558-024-02108-w"),
                "title": "Correct article",
            },
        ]
    }

    result = recovery._select_exact_meta_record(
        payload,
        ("10.1038/s41558-024-02108-w"),
    )

    assert result["title"] == "Correct article"


def test_select_exact_meta_record_rejects_nonmatching_response():
    payload = {"records": [{"doi": ("10.1038/s00000-000-00000-0")}]}

    with pytest.raises(SpringerMetadataRecoveryError):
        (
            recovery._select_exact_meta_record(
                payload,
                ("10.1038/s41558-024-02108-w"),
            )
        )


def test_restricted_access_merges_partial_jats_and_meta_v2(
    tmp_path,
    monkeypatch,
):
    doi = "10.1038/s41558-024-02108-w"

    jats = tmp_path / "paper.jats.xml"

    jats.write_text(
        (
            '<?xml version="1.0" '
            'encoding="UTF-8"?>'
            "<article>"
            "<front>"
            "<journal-meta>"
            "<journal-title-group>"
            "<journal-title>"
            "Nature Climate Change"
            "</journal-title>"
            "</journal-title-group>"
            "</journal-meta>"
            "<article-meta>"
            '<article-id pub-id-type="doi">'
            "10.1038/"
            "s41558-024-02108-w"
            "</article-id>"
            "<title-group>"
            "<article-title>"
            "Elevated urban energy risks"
            "</article-title>"
            "</title-group>"
            "<contrib-group>"
            '<contrib contrib-type="author">'
            "<name>"
            "<surname>Smith</surname>"
            "<given-names>Alice</given-names>"
            "</name>"
            "</contrib>"
            "</contrib-group>"
            "</article-meta>"
            "</front>"
            "</article>"
        ),
        encoding="utf-8",
    )

    metadata_payload = {
        "apiMessage": ("This JSON was provided by Springer Nature"),
        "query": ("doi:10.1038/s41558-024-02108-w"),
        "apiKey": "must-not-be-saved",
        "nextPage": ("/meta/v2/json?api_key=must-not-be-saved"),
        "records": [
            {
                "identifier": ("doi:10.1038/s41558-024-02108-w"),
                "title": ("Elevated urban energy risks"),
                "creators": [
                    {"creator": ("Smith, Alice")},
                    {"creator": ("Jones, Bob")},
                ],
                "journalTitle": ("Nature Climate Change"),
                "publicationDate": ("2024-08-01"),
                "volume": "14",
                "issue": "10",
                "publisherName": ("Springer Nature"),
                "abstract": ("This abstract came from Springer Meta v2."),
                "keyword": [
                    "urban climate",
                    "building energy",
                ],
                "openaccess": False,
                "url": [
                    {
                        "format": "html",
                        "platform": "web",
                        "value": ("https://www.nature.com/articles/s41558-024-02108-w"),
                    }
                ],
            }
        ],
    }

    def fake_fetch_meta_v2_record(
        doi,
        *,
        api_key,
        timeout,
    ):
        assert doi == ("10.1038/s41558-024-02108-w")

        assert api_key == "test-key"
        assert timeout == 10.0

        return (
            metadata_payload,
            metadata_payload["records"][0],
        )

    monkeypatch.setattr(
        recovery,
        "_fetch_meta_v2_record",
        fake_fetch_meta_v2_record,
    )

    raw_md = tmp_path / "paper_raw.md"

    llm_md = tmp_path / "paper_llm.md"

    qa = tmp_path / "qa.json"

    result = write_restricted_access_artifacts(
        doi,
        route="nature",
        paper_directory=(tmp_path),
        raw_markdown_path=(raw_md),
        llm_markdown_path=(llm_md),
        qa_path=qa,
        library_root=(tmp_path.parent),
        api_key="test-key",
        timeout=10.0,
        reason=("Restricted access"),
        existing_xml_path=jats,
    )

    markdown = llm_md.read_text(encoding="utf-8")

    assert "# Elevated urban energy risks" in markdown

    assert "Alice Smith" in markdown

    assert "Smith, Alice" in markdown

    assert "Jones, Bob" in markdown

    assert "Nature Climate Change" in markdown

    assert "2024-08-01" in markdown

    assert "This abstract came from Springer Meta v2." in markdown

    assert "urban climate" in markdown

    assert "building energy" in markdown

    assert "Open access metadata: false" in markdown

    assert result.partial_xml_path == jats

    assert result.metadata_json_path == (tmp_path / "springer_meta.json")

    assert result.metadata_error is None

    assert result.access_json_path.is_file()

    assert qa.is_file()

    meta_artifact = json.loads(result.metadata_json_path.read_text(encoding="utf-8"))

    assert meta_artifact["query"] == ("doi:10.1038/s41558-024-02108-w")

    assert meta_artifact["record"]["title"] == ("Elevated urban energy risks")

    meta_text = result.metadata_json_path.read_text(encoding="utf-8")

    assert "must-not-be-saved" not in meta_text

    access_payload = json.loads(result.access_json_path.read_text(encoding="utf-8"))

    assert access_payload["sources_used"] == [
        "partial_jats_xml",
        "springer_meta_v2",
    ]

    assert "abstract" in access_payload["available_fields"]

    assert access_payload["metadata_error"] is None


def test_restricted_access_meta_v2_only_for_building_simulation(
    tmp_path,
    monkeypatch,
):
    doi = "10.1007/s12273-024-1206-6"

    metadata_payload = {
        "query": ("doi:10.1007/s12273-024-1206-6"),
        "records": [
            {
                "doi": ("10.1007/s12273-024-1206-6"),
                "title": ("Building Simulation Test Article"),
                "creators": [{"creator": ("Test Author")}],
                "publicationName": ("Building Simulation"),
                "publicationDate": ("2024-01-15"),
                "abstract": ("Building Simulation abstract."),
            }
        ],
    }

    def fake_fetch_meta_v2_record(
        doi,
        *,
        api_key,
        timeout,
    ):
        assert doi == ("10.1007/s12273-024-1206-6")

        return (
            metadata_payload,
            metadata_payload["records"][0],
        )

    monkeypatch.setattr(
        recovery,
        "_fetch_meta_v2_record",
        fake_fetch_meta_v2_record,
    )

    result = write_restricted_access_artifacts(
        doi,
        route="building_simulation",
        paper_directory=(tmp_path),
        raw_markdown_path=(tmp_path / "paper_raw.md"),
        llm_markdown_path=(tmp_path / "paper_llm.md"),
        qa_path=(tmp_path / "qa.json"),
        library_root=(tmp_path.parent),
        api_key="test-key",
        timeout=10.0,
        reason=("Restricted access"),
        existing_xml_path=None,
    )

    markdown = result.markdown_path.read_text(encoding="utf-8")

    assert "# Building Simulation Test Article" in markdown

    assert "Test Author" in markdown

    assert "Journal: Building Simulation" in markdown

    assert "Building Simulation abstract." in markdown

    assert result.partial_xml_path is None

    assert result.metadata_json_path == (tmp_path / "springer_meta.json")


def test_restricted_access_survives_meta_v2_failure(
    tmp_path,
    monkeypatch,
):
    doi = "10.1038/s41558-024-02108-w"

    jats = tmp_path / "paper.jats.xml"

    jats.write_text(
        (
            "<article>"
            "<front>"
            "<journal-meta>"
            "<journal-title-group>"
            "<journal-title>"
            "Nature Climate Change"
            "</journal-title>"
            "</journal-title-group>"
            "</journal-meta>"
            "<article-meta>"
            '<article-id pub-id-type="doi">'
            "10.1038/"
            "s41558-024-02108-w"
            "</article-id>"
            "<title-group>"
            "<article-title>"
            "Partial JATS title"
            "</article-title>"
            "</title-group>"
            "</article-meta>"
            "</front>"
            "</article>"
        ),
        encoding="utf-8",
    )

    def fake_fetch_meta_v2_record(
        doi,
        *,
        api_key,
        timeout,
    ):
        raise (SpringerMetadataRecoveryError("Springer Meta v2 returned HTTP 401."))

    monkeypatch.setattr(
        recovery,
        "_fetch_meta_v2_record",
        fake_fetch_meta_v2_record,
    )

    result = write_restricted_access_artifacts(
        doi,
        route="nature",
        paper_directory=(tmp_path),
        raw_markdown_path=(tmp_path / "paper_raw.md"),
        llm_markdown_path=(tmp_path / "paper_llm.md"),
        qa_path=(tmp_path / "qa.json"),
        library_root=(tmp_path.parent),
        api_key="test-key",
        timeout=10.0,
        reason=("Restricted access"),
        existing_xml_path=jats,
    )

    markdown = result.markdown_path.read_text(encoding="utf-8")

    assert "# Partial JATS title" in markdown

    assert "Nature Climate Change" in markdown

    assert result.metadata_json_path is None

    assert result.metadata_error == (
        "SpringerMetadataRecoveryError: Springer Meta v2 returned HTTP 401."
    )

    access_payload = json.loads(result.access_json_path.read_text(encoding="utf-8"))

    assert access_payload["sources_used"] == ["partial_jats_xml"]
