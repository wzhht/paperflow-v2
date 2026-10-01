from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![\w.])"
    r"(?:"
    r"[<>≤≥]?\s*"
    r"[-+−]?"
    r"(?:\d+(?:\.\d+)?|\.\d+)"
    r"(?:[Ee][+−-]?\d+)?"
    r"%?"
    r")"
    r"(?![\w.])"
)


@dataclass(frozen=True)
class JatsStats:
    doi: str | None
    has_body: bool
    section_count: int
    paragraph_count: int
    reference_count: int
    table_count: int
    figure_count: int
    display_formula_count: int
    body_characters: int
    candidate_full_text: bool


@dataclass(frozen=True)
class TableNumericAudit:
    source_tokens: tuple[str, ...]
    markdown_tokens: tuple[str, ...]
    values_match: bool


def inspect_jats_xml(
    path: str | Path,
) -> JatsStats:
    article = _load_article(path)

    doi_values = article.xpath(
        "./*[local-name()='front']//*[local-name()='article-id' and @pub-id-type='doi']/text()"
    )

    doi = str(doi_values[0]).strip().lower() if doi_values else None

    body_nodes = article.xpath("./*[local-name()='body']")

    has_body = bool(body_nodes)

    section_count = len(article.xpath("./*[local-name()='body']//*[local-name()='sec']"))

    paragraph_count = len(article.xpath("./*[local-name()='body']//*[local-name()='p']"))

    reference_count = len(
        article.xpath("./*[local-name()='back']//*[local-name()='ref-list']/*[local-name()='ref']")
    )

    table_count = len(article.xpath("./*[local-name()='body']//*[local-name()='table-wrap']"))

    figure_count = len(article.xpath("./*[local-name()='body']//*[local-name()='fig']"))

    display_formula_count = len(
        article.xpath("./*[local-name()='body']//*[local-name()='disp-formula']")
    )

    body_characters = 0

    if body_nodes:
        body_text = " ".join(
            text.strip() for text in body_nodes[0].itertext() if text and text.strip()
        )
        body_characters = len(body_text)

    candidate_full_text = has_body and paragraph_count >= 10 and body_characters >= 5000

    return JatsStats(
        doi=doi,
        has_body=has_body,
        section_count=section_count,
        paragraph_count=paragraph_count,
        reference_count=reference_count,
        table_count=table_count,
        figure_count=figure_count,
        display_formula_count=display_formula_count,
        body_characters=body_characters,
        candidate_full_text=candidate_full_text,
    )


def audit_jats_table_numeric_values(
    xml_path: str | Path,
    markdown: str,
) -> TableNumericAudit:
    article = _load_article(xml_path)

    source_tokens: list[str] = []

    cells = article.xpath(
        "./*[local-name()='body']"
        "//*[local-name()='table-wrap']"
        "//*[local-name()='th' or local-name()='td']"
    )

    for cell in cells:
        text = " ".join(value.strip() for value in cell.itertext() if value and value.strip())

        source_tokens.extend(_numeric_tokens(text))

    markdown_tokens: list[str] = []

    for line in markdown.splitlines():
        if not _is_markdown_table_row(line):
            continue

        if _is_markdown_separator(line):
            continue

        markdown_tokens.extend(_numeric_tokens(line))

    source_tuple = tuple(source_tokens)
    markdown_tuple = tuple(markdown_tokens)

    return TableNumericAudit(
        source_tokens=source_tuple,
        markdown_tokens=markdown_tuple,
        values_match=(
            source_tuple == markdown_tuple and Counter(source_tuple) == Counter(markdown_tuple)
        ),
    )


def _numeric_tokens(text: str) -> list[str]:
    return [match.strip() for match in _NUMERIC_TOKEN_RE.findall(text)]


def _is_markdown_table_row(line: str) -> bool:
    stripped = line.strip()

    return stripped.startswith("|") and stripped.endswith("|")


def _is_markdown_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]

    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _load_article(
    path: str | Path,
) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
    )

    root = etree.parse(
        str(path),
        parser=parser,
    ).getroot()

    if etree.QName(root).localname == "article":
        return root

    articles = root.xpath(".//*[local-name()='article']")

    if len(articles) == 1:
        return articles[0]

    raise ValueError(f"Expected one JATS article, found {len(articles)}.")
