from __future__ import annotations

import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STRUCTURED_CONTENT_MEMBER = "structured_content.json"

_IGNORED_BLOCK_TYPES = {
    "header",
    "page_number",
    "page_footnote",
    "aside_text",
}

_DISPLAY_EQUATION_TYPES = {
    "equation",
    "display_equation",
    "interline_equation",
}

_HTML_IMG_RE = re.compile(
    r"<img\b[^>]*>",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class MinerURenderStats:
    page_count: int
    block_counts: dict[str, int]
    table_count: int
    image_count: int
    chart_count: int
    display_equations_removed: int
    references_present: bool
    unknown_block_types: tuple[str, ...]


def sanitize_mineru_table_content(
    content: str,
) -> str:
    """
    Remove embedded HTML image tags from MinerU table content.

    MinerU sometimes embeds extracted table-cell images as:

        <img src="images/..."/>

    PaperFlow intentionally removes image assets while preserving the
    surrounding table markup exactly. No table cells, rowspan/colspan
    attributes, textual content, or scientific values are reconstructed.
    """

    return _HTML_IMG_RE.sub(
        "",
        content,
    )


def load_mineru_structured_content(
    path: str | Path,
) -> dict[str, Any]:
    path = Path(path)

    data = json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )

    _validate_structured_content(data)

    return data


def load_mineru_structured_content_from_zip(
    zip_path: str | Path,
) -> dict[str, Any]:
    zip_path = Path(zip_path)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            try:
                content = archive.read(STRUCTURED_CONTENT_MEMBER)

            except KeyError as exc:
                raise ValueError("MinerU ZIP does not contain structured_content.json.") from exc

    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid MinerU ZIP: {zip_path}") from exc

    data = json.loads(content.decode("utf-8"))

    _validate_structured_content(data)

    return data


def convert_mineru_structured_content_to_markdown(
    data: dict[str, Any],
    output_path: str | Path,
) -> tuple[str, MinerURenderStats]:
    """
    Render MinerU structured_content.json into conservative Markdown.

    Policy:

    - document title: preserve
    - headings: preserve
    - text: preserve
    - lists: preserve
    - tables: preserve MinerU representation as-is except embedded <img>
    - table captions/footnotes: preserve
    - image/chart visual content: discard
    - image/chart captions: preserve
    - standalone equations: discard
    - headers/page numbers/aside text/page footnotes: discard
    - unknown block types: preserve textual content conservatively
    """

    _validate_structured_content(data)

    rendered: list[tuple[str, str]] = []

    block_counts: Counter[str] = Counter()

    unknown_types: set[str] = set()

    references_present = False
    equations_removed = 0

    for page in data["pages"]:
        blocks = page.get(
            "blocks",
            [],
        )

        for block in blocks:
            block_type = str(block.get("type") or "").strip()

            block_counts[block_type] += 1

            content = str(block.get("content") or "").strip()

            if block_type in _IGNORED_BLOCK_TYPES:
                continue

            if block_type in _DISPLAY_EQUATION_TYPES:
                equations_removed += 1
                continue

            if block_type == "doc_title":
                if content:
                    rendered.append(
                        (
                            "heading",
                            f"# {content}",
                        )
                    )

                continue

            if block_type == "paragraph_title":
                if not content:
                    continue

                level = _heading_level(content)

                rendered.append(
                    (
                        "heading",
                        (f"{'#' * level} {content}"),
                    )
                )

                if content.casefold() in {
                    "references",
                    "bibliography",
                }:
                    references_present = True

                continue

            if block_type == "text":
                if not content:
                    continue

                if block.get("continues_prev") and rendered and rendered[-1][0] == "text":
                    previous = rendered[-1][1]

                    rendered[-1] = (
                        "text",
                        (previous.rstrip() + " " + content.lstrip()),
                    )

                else:
                    rendered.append(
                        (
                            "text",
                            content,
                        )
                    )

                continue

            if block_type == "list":
                if content:
                    rendered.append(
                        (
                            "list",
                            content,
                        )
                    )

                if block.get("sub_type") == "ref_text":
                    references_present = True

                continue

            if block_type == "table":
                _append_captions(
                    rendered,
                    block,
                )

                if content:
                    table_content = sanitize_mineru_table_content(content)

                    rendered.append(
                        (
                            "table",
                            table_content,
                        )
                    )

                _append_footnotes(
                    rendered,
                    block,
                )

                continue

            if block_type in {
                "image",
                "chart",
            }:
                # Do not render image_source or VLM-produced
                # visual representations.
                #
                # Chart content can contain inferred/approximate
                # values such as "~0.9", so it is deliberately
                # discarded. Captions and footnotes are retained.
                _append_captions(
                    rendered,
                    block,
                )

                _append_footnotes(
                    rendered,
                    block,
                )

                continue

            if block_type:
                unknown_types.add(block_type)

            # Conservative fallback:
            # preserve textual content from an unknown block
            # instead of silently deleting scientific text.
            if content:
                rendered.append(
                    (
                        "text",
                        content,
                    )
                )

    markdown = "\n\n".join(text for _, text in rendered if text).strip()

    markdown += "\n"

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        markdown,
        encoding="utf-8",
    )

    stats = MinerURenderStats(
        page_count=len(data["pages"]),
        block_counts=dict(block_counts),
        table_count=block_counts["table"],
        image_count=block_counts["image"],
        chart_count=block_counts["chart"],
        display_equations_removed=(equations_removed),
        references_present=(references_present),
        unknown_block_types=tuple(sorted(unknown_types)),
    )

    return markdown, stats


def convert_mineru_zip_to_markdown(
    zip_path: str | Path,
    output_path: str | Path,
) -> tuple[str, MinerURenderStats]:
    data = load_mineru_structured_content_from_zip(zip_path)

    return convert_mineru_structured_content_to_markdown(
        data,
        output_path,
    )


def _heading_level(
    title: str,
) -> int:
    """
    Convert numbered MinerU headings into Markdown hierarchy.

    Examples:

        1 Introduction
            -> ##

        3.1 Methodology
            -> ###

        3.7.1 Objective
            -> ####
    """

    match = re.match(
        r"^\s*(\d+(?:\.\d+)*)\s+",
        title,
    )

    if match:
        section_number = match.group(1)

        depth = section_number.count(".") + 1

        return min(
            depth + 1,
            6,
        )

    if re.match(
        r"^\s*Note\s+[A-Z]\d+",
        title,
        flags=re.IGNORECASE,
    ):
        return 3

    return 2


def _append_captions(
    rendered: list[tuple[str, str]],
    block: dict[str, Any],
) -> None:
    captions = block.get(
        "captions",
        [],
    )

    for caption in captions:
        text = str(caption.get("content") or "").strip()

        if text:
            rendered.append(
                (
                    "caption",
                    f"**{text}**",
                )
            )


def _append_footnotes(
    rendered: list[tuple[str, str]],
    block: dict[str, Any],
) -> None:
    footnotes = block.get(
        "footnotes",
        [],
    )

    for footnote in footnotes:
        text = str(footnote.get("content") or "").strip()

        if text:
            rendered.append(
                (
                    "text",
                    text,
                )
            )


def _validate_structured_content(
    data: Any,
) -> None:
    if not isinstance(
        data,
        dict,
    ):
        raise TypeError("MinerU structured content must be a JSON object.")

    pages = data.get("pages")

    if not isinstance(
        pages,
        list,
    ):
        raise TypeError("MinerU structured content does not contain a pages list.")
