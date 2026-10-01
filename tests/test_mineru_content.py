from paperflow.parsers.mineru_content import (
    convert_mineru_structured_content_to_markdown,
)
from paperflow.qa.mineru import (
    audit_mineru_markdown,
)


def _synthetic_mineru_document():
    return {
        "metadata": {
            "producer": {
                "name": "mineru",
                "version": "synthetic",
            }
        },
        "is_full_document": True,
        "pages": [
            {
                "page_idx": 0,
                "blocks": [
                    {
                        "type": "doc_title",
                        "content": "Synthetic building performance study",
                    },
                    {
                        "type": "paragraph_title",
                        "level": 2,
                        "content": "1 Introduction",
                    },
                    {
                        "type": "text",
                        "content": (
                            "This synthetic document tests PaperFlow MinerU rendering. "
                            "Scientific markers include SHGC, CV(RMSE), NMBE, "
                            "R<sup>2</sup>, U-value, WWR, ACH, kWh/m<sup>2</sup>, "
                            "W/m<sup>2</sup>K, °C, and %."
                        ),
                    },
                    {
                        "type": "paragraph_title",
                        "level": 3,
                        "content": "1.1 Synthetic results",
                    },
                    {
                        "type": "table",
                        "content": (
                            "<table>"
                            "<tr>"
                            '<th rowspan="2">Metric</th>'
                            '<th colspan="2">Scenario</th>'
                            "</tr>"
                            "<tr>"
                            "<th>Baseline</th>"
                            "<th>Future</th>"
                            "</tr>"
                            "<tr>"
                            "<td>SHGC</td>"
                            "<td>0.29</td>"
                            "<td>0.35</td>"
                            "</tr>"
                            "<tr>"
                            "<td>Cooling load</td>"
                            "<td>18.5</td>"
                            "<td>23.4</td>"
                            "</tr>"
                            "<tr>"
                            "<td>Tmax</td>"
                            "<td>31.4</td>"
                            "<td>35.0</td>"
                            "</tr>"
                            "</table>"
                        ),
                        "captions": [
                            {
                                "content": "Table 1 Synthetic performance values",
                            }
                        ],
                        "footnotes": [],
                        "image_source": "images/table_1.png",
                    },
                    {
                        "type": "paragraph_title",
                        "level": 2,
                        "content": "References",
                    },
                    {
                        "type": "list",
                        "sub_type": "ref_text",
                        "content": (
                            "- Example Author. Synthetic reference for parser tests. "
                            "Test Journal, 2026."
                        ),
                    },
                ],
            }
        ],
    }


def test_synthetic_mineru_structure():
    data = _synthetic_mineru_document()

    assert len(data["pages"]) == 1
    assert data["is_full_document"] is True
    assert data["metadata"]["producer"]["name"] == "mineru"
    assert data["metadata"]["producer"]["version"] == "synthetic"


def test_synthetic_mineru_renders_markdown(
    tmp_path,
):
    data = _synthetic_mineru_document()

    output = tmp_path / "paper_llm.md"

    markdown, stats = convert_mineru_structured_content_to_markdown(
        data,
        output,
    )

    assert output.read_text(encoding="utf-8") == markdown

    assert stats.page_count == 1
    assert stats.table_count == 1
    assert stats.references_present is True

    assert "# Synthetic building performance study" in markdown
    assert "## 1 Introduction" in markdown
    assert "### 1.1 Synthetic results" in markdown
    assert "## References" in markdown

    assert "SHGC" in markdown
    assert "CV(RMSE)" in markdown
    assert "NMBE" in markdown
    assert "R<sup>2</sup>" in markdown

    assert "rowspan=" in markdown
    assert "colspan=" in markdown

    assert "0.29" in markdown
    assert "0.35" in markdown
    assert "18.5" in markdown
    assert "23.4" in markdown
    assert "31.4" in markdown
    assert "35.0" in markdown

    assert "image_source" not in markdown
    assert "table_1.png" not in markdown

    assert "```mermaid" not in markdown
    assert "<img" not in markdown.lower()


def test_synthetic_mineru_table_content_is_exact(
    tmp_path,
):
    data = _synthetic_mineru_document()

    output = tmp_path / "paper_llm.md"

    markdown, _ = convert_mineru_structured_content_to_markdown(
        data,
        output,
    )

    audit = audit_mineru_markdown(
        data,
        markdown,
    )

    assert audit.source_table_count == 1
    assert audit.matched_table_count == 1

    assert audit.table_content_exact_match is True
    assert audit.table_numeric_values_match is True

    assert audit.has_references is True

    assert audit.remaining_images == 0
    assert audit.remaining_base64 == 0
    assert audit.remaining_display_equations == 0


def test_mineru_removes_html_images_inside_table(
    tmp_path,
):
    """
    Regression for MinerU tables that contain embedded cell images.

    The image tag may contain numeric filenames such as:

        page_4_table_image_12_1.jpg

    Those image-related numbers must not enter the scientific
    table numeric audit.
    """

    data = {
        "pages": [
            {
                "page_idx": 0,
                "blocks": [
                    {
                        "type": "doc_title",
                        "content": "Synthetic paper",
                    },
                    {
                        "type": "table",
                        "content": (
                            "<table>"
                            "<tr>"
                            "<td>Value</td>"
                            "<td>42.5</td>"
                            "</tr>"
                            "<tr>"
                            "<td>Diagram</td>"
                            "<td>"
                            '<img src="images/'
                            "page_4_table_"
                            'image_12_1.jpg"/>'
                            "</td>"
                            "</tr>"
                            "</table>"
                        ),
                        "captions": [
                            {
                                "content": "Table 1 Synthetic test",
                            }
                        ],
                        "footnotes": [],
                        "image_source": "images/page_4_table.jpg",
                    },
                    {
                        "type": "paragraph_title",
                        "level": 2,
                        "content": "References",
                    },
                    {
                        "type": "list",
                        "sub_type": "ref_text",
                        "content": "- Example reference.",
                    },
                ],
            }
        ]
    }

    output = tmp_path / "paper_llm.md"

    markdown, stats = convert_mineru_structured_content_to_markdown(
        data,
        output,
    )

    assert stats.table_count == 1

    assert "<img" not in markdown.lower()
    assert "page_4_table_image_12_1.jpg" not in markdown

    assert "<td>42.5</td>" in markdown
    assert "<td>Diagram</td>" in markdown
    assert "<td></td>" in markdown

    audit = audit_mineru_markdown(
        data,
        markdown,
    )

    assert audit.source_table_count == 1
    assert audit.matched_table_count == 1

    assert audit.table_content_exact_match is True

    assert audit.source_numeric_tokens == 1
    assert audit.final_numeric_tokens == 1

    assert audit.table_numeric_values_match is True
    assert audit.remaining_images == 0
    assert audit.has_references is True
