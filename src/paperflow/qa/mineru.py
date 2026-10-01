from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from paperflow.parsers.mineru_content import (
    sanitize_mineru_table_content,
)

_NUMERIC_TOKEN_RE = re.compile(
    r"[+−\-±]?"
    r"(?:\d+(?:\.\d+)?|\.\d+)"
    r"(?:[Ee][+−\-]?\d+)?"
    r"%?"
)

_HTML_IMG_RE = re.compile(
    r"<img\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class MinerUMarkdownAudit:
    source_table_count: int
    matched_table_count: int
    source_numeric_tokens: int
    final_numeric_tokens: int
    table_content_exact_match: bool
    table_numeric_values_match: bool
    has_references: bool
    remaining_images: int
    remaining_base64: int
    remaining_display_equations: int
    private_use_characters: int
    mojibake: bool


def audit_mineru_markdown(
    structured_content: dict[str, Any],
    markdown: str,
) -> MinerUMarkdownAudit:
    """
    Audit the rendered MinerU Markdown.

    Table comparison uses the same permitted transformation as
    the renderer: embedded HTML <img> elements are removed first.

    Everything else in the table is expected to survive exactly.
    """

    source_tables = _source_tables(structured_content)

    source_tokens: list[str] = []
    final_tokens: list[str] = []

    matched = 0
    search_offset = 0

    for table in source_tables:
        source_tokens.extend(_numeric_tokens(table))

        index = markdown.find(
            table,
            search_offset,
        )

        if index < 0:
            continue

        matched += 1

        matched_text = markdown[index : index + len(table)]

        final_tokens.extend(_numeric_tokens(matched_text))

        search_offset = index + len(table)

    exact_match = matched == len(source_tables)

    numeric_match = exact_match and source_tokens == final_tokens

    private_use = sum(1 for char in markdown if ("\ue000" <= char <= "\uf8ff"))

    mojibake = any(
        marker in markdown
        for marker in (
            "Ã",
            "Â",
            "â€",
            "\ufffd",
        )
    )

    markdown_images = markdown.count("![")

    image_source_markers = markdown.count("image_source")

    html_images = len(_HTML_IMG_RE.findall(markdown))

    remaining_images = markdown_images + image_source_markers + html_images

    remaining_base64 = markdown.lower().count("data:image")

    remaining_display_equations = markdown.count("$$") + markdown.count("```math")

    return MinerUMarkdownAudit(
        source_table_count=len(source_tables),
        matched_table_count=(matched),
        source_numeric_tokens=len(source_tokens),
        final_numeric_tokens=len(final_tokens),
        table_content_exact_match=(exact_match),
        table_numeric_values_match=(numeric_match),
        has_references=(_has_references(markdown)),
        remaining_images=(remaining_images),
        remaining_base64=(remaining_base64),
        remaining_display_equations=(remaining_display_equations),
        private_use_characters=(private_use),
        mojibake=mojibake,
    )


def _source_tables(
    data: dict[str, Any],
) -> list[str]:
    """
    Return the canonical PaperFlow representation of each
    MinerU source table.

    The only allowed transformation is embedded HTML image
    removal. This keeps table structure and scientific values
    unchanged while satisfying the no-images contract.
    """

    tables: list[str] = []

    for page in data.get(
        "pages",
        [],
    ):
        blocks = page.get(
            "blocks",
            [],
        )

        for block in blocks:
            if block.get("type") != "table":
                continue

            content = str(block.get("content") or "").strip()

            if not content:
                continue

            tables.append(sanitize_mineru_table_content(content))

    return tables


def _numeric_tokens(
    text: str,
) -> list[str]:
    return _NUMERIC_TOKEN_RE.findall(text)


def _has_references(
    markdown: str,
) -> bool:
    return (
        re.search(
            r"^#{1,6}\s+"
            r"(?:References|Bibliography)"
            r"\s*$",
            markdown,
            flags=(re.IGNORECASE | re.MULTILINE),
        )
        is not None
    )
