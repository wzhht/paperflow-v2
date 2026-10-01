import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

DISPLAY_MATH_RE = re.compile(
    r'(?ms)(?:^[ \t]*<a id="e[^"]+"></a>[ \t]*\r?\n)?'
    r"^[ \t]*\$\$[ \t]*\r?\n"
    r".*?"
    r"^[ \t]*\$\$(?:[ \t]+\([^)]+\))?[ \t]*(?:\r?\n)?"
)

TABLE_ANCHOR_RE = re.compile(r'<a id="(?P<id>t[^"]+)"></a>')

TABLE_ID_RE = re.compile(r'<a id="(t[^"]+)"></a>')

REFERENCE_ID_RE = re.compile(r'(?m)^<a id="(b[^"]+)"></a>\s*$')

DISPLAY_DELIMITER_RE = re.compile(r"(?m)^[ \t]*\$\$")


@dataclass(frozen=True)
class ElsevierMarkdownStats:
    display_equations_removed: int
    float_table_ids: tuple[str, ...]
    relocated_table_ids: tuple[str, ...]
    missing_float_table_ids: tuple[str, ...]
    image_only_float_table_ids: tuple[str, ...]
    table_count_markdown: int
    reference_count_markdown: int
    has_results: bool
    has_conclusion: bool
    has_references: bool
    remaining_display_math: int


def _parse_xml(
    xml_content: bytes | str,
) -> etree._Element:
    if isinstance(xml_content, str):
        xml_content = xml_content.encode("utf-8")

    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
    )

    return etree.fromstring(
        xml_content,
        parser=parser,
    )


def _find_float_table_ids(
    xml_content: bytes | str,
) -> tuple[str, ...]:
    root = _parse_xml(xml_content)

    table_ids: list[str] = []

    nodes = root.xpath("//*[local-name()='float-anchor']")

    for node in nodes:
        refid = node.get("refid")

        if not refid:
            continue

        if not refid.startswith("t"):
            continue

        if refid not in table_ids:
            table_ids.append(refid)

    return tuple(table_ids)


def _classify_missing_float_tables(
    xml_content: bytes | str,
    missing_table_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Split missing float tables into true missing tables and image-only tables.

    Elsevier sometimes represents a table as a caption plus an external image
    object (for example ``<ce:link locator="fx1001"/>``) with no CALS
    ``tgroup`` / ``entry`` cell data. In that case PaperFlow cannot preserve
    exact table values from the structured XML, so the table is recorded as an
    image-only warning rather than a structured-table loss.

    A table that contains structured CALS rows/cells is never downgraded.
    """

    if not missing_table_ids:
        return (), ()

    root = _parse_xml(xml_content)

    true_missing: list[str] = []
    image_only: list[str] = []

    for table_id in missing_table_ids:
        tables = root.xpath(
            "//*[local-name()='table' and @id=$table_id]",
            table_id=table_id,
        )

        if not tables:
            true_missing.append(table_id)
            continue

        table = tables[0]

        has_structured_cells = bool(
            table.xpath(".//*[local-name()='tgroup' or local-name()='entry' or local-name()='row']")
        )

        has_external_image = bool(
            table.xpath(
                ".//*[local-name()='link' or local-name()='graphic' or local-name()='inline-graphic']"
            )
        )

        if has_external_image and not has_structured_cells:
            image_only.append(table_id)
        else:
            true_missing.append(table_id)

    return (
        tuple(true_missing),
        tuple(image_only),
    )


def _extract_table_block(
    markdown: str,
    table_id: str,
) -> tuple[int, int, str] | None:
    """
    Extract one rendered Markdown table block.

    Litdown normally emits a table anchor on its own line, but some
    Elsevier documents place the table anchor at the end of a previous
    figure-caption line. The anchor therefore must be located anywhere
    in the line instead of requiring a full-line match.
    """

    lines = markdown.splitlines(keepends=True)

    offsets = [0]

    for line in lines:
        offsets.append(offsets[-1] + len(line))

    anchor_index: int | None = None
    anchor_start: int | None = None
    anchor_end_in_line: int | None = None

    for index, line in enumerate(lines):
        for match in TABLE_ANCHOR_RE.finditer(line):
            if match.group("id") != table_id:
                continue

            anchor_index = index
            anchor_start = offsets[index] + match.start()
            anchor_end_in_line = match.end()
            break

        if anchor_index is not None:
            break

    if anchor_index is None or anchor_start is None or anchor_end_in_line is None:
        return None

    anchor_line = lines[anchor_index]
    remainder = anchor_line[anchor_end_in_line:].strip()

    if remainder:
        if not remainder.startswith("**Table"):
            return None
        index = anchor_index + 1
    else:
        index = anchor_index + 1

        while index < len(lines) and not lines[index].strip():
            index += 1

        if index >= len(lines):
            return None

        if not lines[index].lstrip().startswith("**Table"):
            return None

        index += 1

    while index < len(lines) and not lines[index].strip():
        index += 1

    if index >= len(lines):
        return None

    if not lines[index].lstrip().startswith("|"):
        return None

    while index < len(lines) and lines[index].lstrip().startswith("|"):
        index += 1

    possible_note = index

    while possible_note < len(lines) and not lines[possible_note].strip():
        possible_note += 1

    if possible_note < len(lines):
        stripped = lines[possible_note].lstrip()

        is_note = stripped.startswith("*") or re.match(
            r"(?i)^notes?\s*:",
            stripped,
        )

        if is_note:
            index = possible_note + 1

            while index < len(lines):
                stripped = lines[index].strip()

                if not stripped:
                    break

                if TABLE_ANCHOR_RE.search(stripped):
                    break

                if stripped.startswith("#"):
                    break

                index += 1

    end = offsets[index]

    return (
        anchor_start,
        end,
        markdown[anchor_start:end],
    )


def _reference_paragraph_end(
    markdown: str,
    table_id: str,
) -> int | None:
    references_position = markdown.find("## References")

    if references_position == -1:
        search_end = len(markdown)
    else:
        search_end = references_position

    reference_position = markdown.find(
        f"(#{table_id})",
        0,
        search_end,
    )

    if reference_position == -1:
        return None

    paragraph_end = re.search(
        r"\r?\n[ \t]*\r?\n",
        markdown[reference_position:search_end],
    )

    if paragraph_end is None:
        return search_end

    return reference_position + paragraph_end.end()


def _relocate_float_tables(
    markdown: str,
    xml_content: bytes | str,
) -> tuple[
    str,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    float_table_ids = _find_float_table_ids(xml_content)

    relocated: list[str] = []
    missing: list[str] = []

    cleaned = markdown

    for table_id in float_table_ids:
        block = _extract_table_block(
            cleaned,
            table_id,
        )

        if block is None:
            missing.append(table_id)
            continue

        start, end, block_text = block

        target = _reference_paragraph_end(
            cleaned,
            table_id,
        )

        if target is None:
            continue

        if target <= start:
            between = cleaned[target:start]

            if not between.strip():
                continue

        if target >= start:
            continue

        line_start = (
            max(
                cleaned.rfind("\n", 0, start),
                cleaned.rfind("\r", 0, start),
            )
            + 1
        )

        anchor_is_inline = bool(cleaned[line_start:start].strip())

        removal_replacement = "\n" if anchor_is_inline else ""

        cleaned = cleaned[:start] + removal_replacement + cleaned[end:]

        block_text = block_text.strip("\r\n")

        cleaned = cleaned[:target] + block_text + "\n\n" + cleaned[target:]

        relocated.append(table_id)

    return (
        cleaned,
        tuple(relocated),
        tuple(missing),
        float_table_ids,
    )


def _normalize_table_cell(
    cell: str,
) -> str:
    text = cell.strip()

    # Normalize non-breaking spaces.
    text = text.replace(
        "\u00a0",
        " ",
    )

    # HTML line breaks add no useful semantic
    # information for LLM-oriented tables.
    text = re.sub(
        r"(?i)<br\s*/?>",
        " ",
        text,
    )

    text = text.strip()

    # Litdown can emit \boldsymbol{<latin>} inside inline math.
    # Some Markdown math renderers display \boldsymbol as an
    # unsupported command (red text). For simple Latin variables,
    # \mathbf preserves the intended bold variable without changing
    # the symbol, subscript, or surrounding scientific values.
    text = re.sub(
        r"\\boldsymbol\{([A-Za-z])\}",
        r"\\mathbf{\1}",
        text,
    )

    # Undo escaped Markdown asterisks.
    #
    # Examples:
    # \*QHeating\*
    # **VBASELINE \*\* / \*\*QH**
    text = text.replace(
        r"\*",
        "*",
    )

    # Remove Markdown bold fragments while
    # preserving their text.
    #
    # **VBASELINE** -> VBASELINE
    # **VBASELINE ** / **QH**
    # -> VBASELINE / QH
    bold_pattern = re.compile(r"(?<!\S)\*\*\s*(.*?)\s*\*\*(?!\S)")

    previous = None

    while previous != text:
        previous = text

        text = bold_pattern.sub(
            r"\1",
            text,
        )

    # Remove Markdown italic fragments while
    # preserving their text.
    #
    # *QHeating* -> QHeating
    #
    # Significance suffixes remain:
    # 0.35*
    # 0.21**
    italic_pattern = re.compile(r"(?<!\S)\*\s*(.*?)\s*\*(?!\S)")

    previous = None

    while previous != text:
        previous = text

        text = italic_pattern.sub(
            r"\1",
            text,
        )

    # Handle malformed emphasis surrounding
    # the entire cell.
    whole_cell_emphasis = re.fullmatch(
        r"\*+\s*(.*?)\s*\*+",
        text,
        flags=re.DOTALL,
    )

    if whole_cell_emphasis is not None:
        text = whole_cell_emphasis.group(1).strip()

    # Collapse formatting-generated spaces,
    # but DO NOT alter "/" because it can
    # belong to scientific units such as:
    #
    # kWh/m2
    # W/m2K
    # kg/m3
    text = re.sub(
        r"[ \t]{2,}",
        " ",
        text,
    )

    return text.strip()


def _is_table_separator_row(
    line: str,
) -> bool:
    return bool(
        re.fullmatch(
            r"\s*\|(?:\s*:?-+:?\s*\|)+\s*",
            line,
        )
    )


def _normalize_table_cells(
    markdown: str,
) -> str:
    output: list[str] = []

    for line in markdown.splitlines():
        stripped = line.lstrip()

        if not stripped.startswith("|"):
            output.append(line)
            continue

        if _is_table_separator_row(line):
            output.append(line)
            continue

        parts = line.split("|")

        if len(parts) < 3:
            output.append(line)
            continue

        cells = [_normalize_table_cell(cell) for cell in parts[1:-1]]

        output.append("| " + " | ".join(cells) + " |")

    return "\n".join(output)


def _has_heading(
    markdown: str,
    title: str,
) -> bool:
    pattern = re.compile(
        rf"(?mi)^#{{1,6}}\s+"
        rf"(?:\d+(?:\.\d+)*\s+)?"
        rf"{re.escape(title)}\s*$"
    )

    return bool(pattern.search(markdown))


def clean_elsevier_markdown(
    markdown: str,
    xml_content: bytes | str,
) -> tuple[
    str,
    ElsevierMarkdownStats,
]:
    without_math, equation_count = DISPLAY_MATH_RE.subn(
        "\n\n",
        markdown,
    )

    (
        cleaned,
        relocated_table_ids,
        missing_float_table_ids,
        float_table_ids,
    ) = _relocate_float_tables(
        without_math,
        xml_content,
    )

    (
        missing_float_table_ids,
        image_only_float_table_ids,
    ) = _classify_missing_float_tables(
        xml_content,
        missing_float_table_ids,
    )

    cleaned = _normalize_table_cells(cleaned)

    cleaned = re.sub(
        r"\n{3,}",
        "\n\n",
        cleaned,
    )

    cleaned = cleaned.strip() + "\n"

    table_ids = set(TABLE_ID_RE.findall(cleaned))

    reference_ids = set(REFERENCE_ID_RE.findall(cleaned))

    stats = ElsevierMarkdownStats(
        display_equations_removed=(equation_count),
        float_table_ids=(float_table_ids),
        relocated_table_ids=(relocated_table_ids),
        missing_float_table_ids=(missing_float_table_ids),
        image_only_float_table_ids=(image_only_float_table_ids),
        table_count_markdown=len(table_ids),
        reference_count_markdown=len(reference_ids),
        has_results=_has_heading(
            cleaned,
            "Results",
        ),
        has_conclusion=_has_heading(
            cleaned,
            "Conclusion",
        ),
        has_references=_has_heading(
            cleaned,
            "References",
        ),
        remaining_display_math=len(DISPLAY_DELIMITER_RE.findall(cleaned)),
    )

    return (
        cleaned,
        stats,
    )


def clean_elsevier_markdown_file(
    raw_markdown_path: str | Path,
    xml_path: str | Path,
    output_path: str | Path,
) -> ElsevierMarkdownStats:
    raw_markdown_path = Path(raw_markdown_path)

    xml_path = Path(xml_path)

    output_path = Path(output_path)

    markdown = raw_markdown_path.read_text(encoding="utf-8")

    xml_content = xml_path.read_bytes()

    cleaned, stats = clean_elsevier_markdown(
        markdown,
        xml_content,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        cleaned,
        encoding="utf-8",
    )

    return stats
