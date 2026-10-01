from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

_BLOCK_TAGS = {
    "fig",
    "table-wrap",
    "list",
    "disp-formula",
}


def convert_jats_xml_to_markdown(
    input_path: str | Path,
    output_path: str | Path,
) -> str:
    article = _load_article(input_path)
    markdown = _render_article(article)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")

    return markdown


def _load_article(path: str | Path) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
    )

    root = etree.parse(str(path), parser=parser).getroot()

    if _local_name(root) == "article":
        return root

    articles = root.xpath(".//*[local-name()='article']")

    if len(articles) == 1:
        return articles[0]

    raise ValueError(f"Expected one JATS article, found {len(articles)}.")


def _render_article(article: etree._Element) -> str:
    lines: list[str] = []

    title = _first_text(
        article,
        "./*[local-name()='front']//*[local-name()='article-title'][1]",
    )

    doi = _first_text(
        article,
        "./*[local-name()='front']//*[local-name()='article-id' and @pub-id-type='doi'][1]",
    )

    journal = _first_text(
        article,
        "./*[local-name()='front']//*[local-name()='journal-title'][1]",
    )

    published = _publication_date(article)
    authors = _authors(article)

    lines.extend(
        [
            f"# {title or doi or 'Untitled article'}",
            "",
        ]
    )

    if doi:
        lines.append(f"- DOI: {doi}")

    if journal:
        lines.append(f"- Journal: {journal}")

    if published:
        lines.append(f"- Published: {published}")

    if authors:
        lines.append(f"- Authors: {', '.join(authors)}")

    abstract = _abstract(article)

    if abstract:
        lines.extend(
            [
                "",
                "## Abstract",
                "",
                abstract,
            ]
        )

    body = article.xpath("./*[local-name()='body']")

    if body:
        for section in body[0].xpath("./*[local-name()='sec']"):
            lines.extend(_render_section(section, level=2))

        # Some valid JATS documents place body paragraphs directly
        # under <body> instead of wrapping them in <sec>.
        for paragraph in body[0].xpath("./*[local-name()='p']"):
            for block in _render_paragraph(paragraph):
                lines.extend(["", block])

    back = article.xpath("./*[local-name()='back']")

    if back:
        lines.extend(_render_back(back[0]))

    markdown = "\n".join(lines)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    return markdown.strip() + "\n"


def _render_section(
    section: etree._Element,
    level: int,
) -> list[str]:
    lines: list[str] = []

    title = _first_text(
        section,
        "./*[local-name()='title'][1]",
    )

    if title:
        heading_level = min(max(level, 2), 6)
        lines.extend(
            [
                "",
                f"{'#' * heading_level} {title}",
            ]
        )

    child_level = level + 1 if title else level

    for child in section:
        if not isinstance(child.tag, str):
            continue

        tag = _local_name(child)

        if tag == "title":
            continue

        if tag == "p":
            for block in _render_paragraph(child):
                lines.extend(["", block])

        elif tag == "sec":
            lines.extend(
                _render_section(
                    child,
                    level=min(child_level, 6),
                )
            )

        elif tag == "table-wrap":
            table = _render_table(child)
            if table:
                lines.extend(["", table])

        elif tag == "fig":
            figure = _render_figure(child)
            if figure:
                lines.extend(["", figure])

        elif tag == "list":
            rendered_list = _render_list(child)
            if rendered_list:
                lines.extend(["", rendered_list])

        # Display equations are intentionally omitted.
        elif tag == "disp-formula":
            continue

    return lines


def _render_paragraph(
    paragraph: etree._Element,
) -> list[str]:
    blocks: list[str] = []
    text_buffer: list[str] = []

    def flush_text() -> None:
        text = _collapse_ws("".join(text_buffer))

        if text:
            blocks.append(text)

        text_buffer.clear()

    if paragraph.text:
        text_buffer.append(paragraph.text)

    for child in paragraph:
        if not isinstance(child.tag, str):
            if child.tail:
                text_buffer.append(child.tail)
            continue

        tag = _local_name(child)

        if tag in _BLOCK_TAGS:
            flush_text()

            block = ""

            if tag == "fig":
                block = _render_figure(child)

            elif tag == "table-wrap":
                block = _render_table(child)

            elif tag == "list":
                block = _render_list(child)

            # disp-formula is intentionally discarded.

            if block:
                blocks.append(block)

        else:
            text_buffer.append(_render_inline_child(child))

        if child.tail:
            text_buffer.append(child.tail)

    flush_text()

    return blocks


def _render_inline_child(node: etree._Element) -> str:
    tag = _local_name(node)

    if tag == "sup":
        value = _collapse_ws(_inline_text(node))

        if not value:
            return ""

        contains_reference = bool(node.xpath(".//*[local-name()='xref' and @ref-type='bibr']"))

        if contains_reference:
            return f"[{value}]"

        return f"<sup>{value}</sup>"

    if tag == "sub":
        value = _collapse_ws(_inline_text(node))
        return f"<sub>{value}</sub>" if value else ""

    if tag == "xref":
        return _collapse_ws(_inline_text(node))

    if tag == "ext-link":
        text = _collapse_ws(_inline_text(node))

        if text:
            return text

        return str(node.get(XLINK_HREF) or "")

    if tag == "inline-formula":
        return _render_inline_formula(node)

    return _inline_text(node)


def _render_inline_formula(node: etree._Element) -> str:
    tex_math = node.xpath(".//*[local-name()='tex-math'][1]")

    if tex_math:
        raw_tex = "".join(tex_math[0].itertext())
        cleaned_tex = _clean_inline_tex_math(raw_tex)

        if cleaned_tex:
            return f"${cleaned_tex}$"

    mathml = node.xpath(".//*[local-name()='math'][1]")

    if mathml:
        text = _collapse_ws("".join(mathml[0].itertext()))

        if text:
            return f"${text}$"

    # Last-resort fallback for unusual JATS that contains neither
    # tex-math nor MathML. Avoid recursive rendering here because
    # alternatives commonly contain multiple representations of
    # the same formula.
    text = _collapse_ws("".join(node.itertext()))
    return text


def _clean_inline_tex_math(text: str) -> str:
    cleaned = text.strip()

    document_match = re.search(
        r"\\begin\{document\}(.*?)\\end\{document\}",
        cleaned,
        flags=re.DOTALL,
    )

    if document_match:
        cleaned = document_match.group(1).strip()
    else:
        # Be conservative with non-wrapper TeX, but remove the known
        # Springer compilation preamble if it appears without an
        # explicit document block.
        cleaned = re.sub(
            r"\\documentclass(?:\[[^\]]*\])?\{[^}]*\}",
            "",
            cleaned,
        )
        cleaned = re.sub(
            r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\}",
            "",
            cleaned,
        )
        cleaned = re.sub(
            r"\\setlength\{[^}]*\}\{[^}]*\}",
            "",
            cleaned,
        )
        cleaned = cleaned.replace("\\begin{document}", "")
        cleaned = cleaned.replace("\\end{document}", "")

    cleaned = _collapse_ws(cleaned)

    delimiter_pairs = (
        ("$$", "$$"),
        (r"\[", r"\]"),
        (r"\(", r"\)"),
        ("$", "$"),
    )

    for opening, closing in delimiter_pairs:
        if cleaned.startswith(opening) and cleaned.endswith(closing):
            inner = cleaned[len(opening) : len(cleaned) - len(closing)].strip()
            if inner:
                cleaned = inner
            break

    return cleaned.strip()


def _inline_text(node: etree._Element) -> str:
    parts: list[str] = []

    if node.text:
        parts.append(node.text)

    for child in node:
        if not isinstance(child.tag, str):
            if child.tail:
                parts.append(child.tail)
            continue

        if _local_name(child) not in _BLOCK_TAGS:
            parts.append(_render_inline_child(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


def _render_figure(figure: etree._Element) -> str:
    label = _first_text(
        figure,
        "./*[local-name()='label'][1]",
    )

    caption = _first_text(
        figure,
        "./*[local-name()='caption'][1]",
    )

    if label and caption:
        return f"**{_label_with_period(label)}** {caption}"

    if label:
        return f"**{label}**"

    if caption:
        return f"**{caption}**"

    return ""


def _render_table(table_wrap: etree._Element) -> str:
    _require_simple_table(table_wrap)

    label = _first_text(
        table_wrap,
        "./*[local-name()='label'][1]",
    )

    caption = _first_text(
        table_wrap,
        "./*[local-name()='caption'][1]",
    )

    lines: list[str] = []

    if label and caption:
        lines.extend(
            [
                f"**{_label_with_period(label)}** {caption}",
                "",
            ]
        )
    elif label:
        lines.extend([f"**{label}**", ""])
    elif caption:
        lines.extend([f"**{caption}**", ""])

    tables = table_wrap.xpath("./*[local-name()='table'][1]")

    if tables:
        table = tables[0]

        header_rows = table.xpath("./*[local-name()='thead']/*[local-name()='tr']")

        body_rows = table.xpath("./*[local-name()='tbody']/*[local-name()='tr']")

        rendered_header_rows = [_table_row(row) for row in header_rows]
        rendered_body_rows = [_table_row(row) for row in body_rows]

        all_rows = rendered_header_rows + rendered_body_rows

        width = max(
            (len(row) for row in all_rows),
            default=1,
        )

        if rendered_header_rows:
            header = _pad_row(
                rendered_header_rows[0],
                width,
            )
            remaining_rows = rendered_header_rows[1:] + rendered_body_rows
        else:
            # Do not invent scientific headers.
            header = [""] * width
            remaining_rows = rendered_body_rows

        lines.append(_markdown_table_row(header))
        lines.append(_markdown_table_row(["---"] * width))

        for row in remaining_rows:
            lines.append(_markdown_table_row(_pad_row(row, width)))

    foot = _first_text(
        table_wrap,
        "./*[local-name()='table-wrap-foot'][1]",
    )

    if foot:
        lines.extend(["", foot])

    return "\n".join(lines).strip()


def _require_simple_table(
    table_wrap: etree._Element,
) -> None:
    cells = table_wrap.xpath(".//*[local-name()='th' or local-name()='td']")

    for cell in cells:
        for attribute in ("rowspan", "colspan"):
            value = str(cell.get(attribute) or "").strip()

            if value and value != "1":
                raise ValueError(
                    "JATS table contains rowspan/colspan; refusing unsafe automatic conversion."
                )


def _table_row(row: etree._Element) -> list[str]:
    cells = row.xpath("./*[local-name()='th' or local-name()='td']")

    # Important: never remove empty cells. Doing so can shift
    # scientific values into the wrong column.
    return [_collapse_ws(_inline_text(cell)) for cell in cells]


def _pad_row(
    row: list[str],
    width: int,
) -> list[str]:
    return row + [""] * max(width - len(row), 0)


def _markdown_table_row(row: list[str]) -> str:
    escaped = [cell.replace("|", r"\|").replace("\n", " ") for cell in row]

    return "| " + " | ".join(escaped) + " |"


def _render_list(list_node: etree._Element) -> str:
    ordered = str(list_node.get("list-type") or "").lower() == "order"

    lines: list[str] = []

    items = list_node.xpath("./*[local-name()='list-item']")

    for index, item in enumerate(items, start=1):
        paragraphs = item.xpath("./*[local-name()='p']")

        if paragraphs:
            text = _collapse_ws(" ".join(_inline_text(paragraph) for paragraph in paragraphs))
        else:
            text = _collapse_ws(_inline_text(item))

        if not text:
            continue

        prefix = f"{index}." if ordered else "-"
        lines.append(f"{prefix} {text}")

    return "\n".join(lines)


def _render_back(back: etree._Element) -> list[str]:
    lines: list[str] = []

    acknowledgements = back.xpath("./*[local-name()='ack'][1]")

    if acknowledgements:
        title = (
            _first_text(
                acknowledgements[0],
                "./*[local-name()='title'][1]",
            )
            or "Acknowledgements"
        )

        lines.extend(["", f"## {title}"])

        for paragraph in acknowledgements[0].xpath("./*[local-name()='p']"):
            for block in _render_paragraph(paragraph):
                lines.extend(["", block])

    for section in back.xpath("./*[local-name()='sec']"):
        lines.extend(
            _render_section(
                section,
                level=2,
            )
        )

    reference_lists = back.xpath("./*[local-name()='ref-list'][1]")

    if reference_lists:
        lines.extend(
            [
                "",
                "## References",
                "",
            ]
        )

        references = reference_lists[0].xpath("./*[local-name()='ref']")

        for reference in references:
            rendered = _render_reference(reference)

            if rendered:
                lines.extend([rendered, ""])

    return lines


def _render_reference(reference: etree._Element) -> str:
    label = _first_text(
        reference,
        "./*[local-name()='label'][1]",
    )

    citations = reference.xpath(
        "./*[local-name()='mixed-citation' or local-name()='element-citation'][1]"
    )

    source = citations[0] if citations else reference
    text = _reference_text(source)

    return " ".join(part for part in (label, text) if part)


def _reference_text(node: etree._Element) -> str:
    parts: list[str] = []

    def walk(current: etree._Element) -> None:
        if current.text:
            parts.append(current.text)

        for child in current:
            if not isinstance(child.tag, str):
                if child.tail:
                    parts.append(child.tail)
                continue

            if _local_name(child) == "etal":
                parts.append(" et al. ")
            else:
                walk(child)

            if child.tail:
                parts.append(child.tail)
            else:
                parts.append(" ")

    walk(node)

    return _collapse_ws("".join(parts))


def _authors(article: etree._Element) -> list[str]:
    authors: list[str] = []

    contributors = article.xpath(
        "./*[local-name()='front']//*[local-name()='contrib' and @contrib-type='author']"
    )

    for contributor in contributors:
        given = _first_text(
            contributor,
            "./*[local-name()='name']/*[local-name()='given-names'][1]",
        )

        surname = _first_text(
            contributor,
            "./*[local-name()='name']/*[local-name()='surname'][1]",
        )

        name = " ".join(part for part in (given, surname) if part)

        if name:
            authors.append(name)

    return authors


def _abstract(article: etree._Element) -> str:
    abstracts = article.xpath(
        "./*[local-name()='front']//*[local-name()='abstract' and not(@abstract-type)][1]"
    )

    if not abstracts:
        return ""

    paragraphs = abstracts[0].xpath("./*[local-name()='p']")

    return "\n\n".join(
        _collapse_ws(_inline_text(paragraph))
        for paragraph in paragraphs
        if _collapse_ws(_inline_text(paragraph))
    )


def _publication_date(article: etree._Element) -> str:
    dates = article.xpath(
        "./*[local-name()='front']//*[local-name()='pub-date' and @date-type='pub'][1]"
    )

    if not dates:
        return ""

    date = dates[0]

    year = _first_text(
        date,
        "./*[local-name()='year'][1]",
    )

    month = _first_text(
        date,
        "./*[local-name()='month'][1]",
    )

    day = _first_text(
        date,
        "./*[local-name()='day'][1]",
    )

    if not year:
        return ""

    parts = [year]

    if month:
        parts.append(month.zfill(2) if month.isdigit() else month)

    if day:
        parts.append(day.zfill(2) if day.isdigit() else day)

    return "-".join(parts)


def _first_text(
    node: etree._Element,
    xpath: str,
) -> str:
    matches = node.xpath(xpath)

    if not matches:
        return ""

    value = matches[0]

    if isinstance(value, str):
        return _collapse_ws(value)

    return _collapse_ws(" ".join(value.itertext()))


def _label_with_period(label: str) -> str:
    if label.endswith((".", ":")):
        return label

    return f"{label}."


def _local_name(node: etree._Element) -> str:
    return etree.QName(node).localname


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
