from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from paperflow.parsers.mineru_content import (
    convert_mineru_zip_to_markdown,
    load_mineru_structured_content_from_zip,
)
from paperflow.qa.mineru import (
    audit_mineru_markdown,
)

OUTPUT_DIR = Path("workspace/mineru_batch/output")


def main() -> None:
    zip_paths = sorted(OUTPUT_DIR.glob("*/mineru.zip"))

    if not zip_paths:
        raise RuntimeError(f"No MinerU ZIP files found under {OUTPUT_DIR}.")

    print(
        "MinerU ZIP files =",
        len(zip_paths),
    )

    for zip_path in zip_paths:
        paper_dir = zip_path.parent

        markdown_path = paper_dir / "paper_llm.md"

        qa_path = paper_dir / "qa_rerender.json"

        print()
        print("=" * 78)
        print(paper_dir.name)
        print("=" * 78)

        data = load_mineru_structured_content_from_zip(zip_path)

        markdown, stats = convert_mineru_zip_to_markdown(
            zip_path,
            markdown_path,
        )

        audit = audit_mineru_markdown(
            data,
            markdown,
        )

        payload = {
            "render": asdict(stats),
            "audit": asdict(audit),
        }

        qa_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            "tables =",
            (f"{audit.matched_table_count}/{audit.source_table_count}"),
        )

        print(
            "table exact =",
            audit.table_content_exact_match,
        )

        print(
            "numeric match =",
            audit.table_numeric_values_match,
        )

        print(
            "references =",
            audit.has_references,
        )

        print(
            "remaining images =",
            audit.remaining_images,
        )

        print(
            "remaining base64 =",
            audit.remaining_base64,
        )

        print(
            "remaining display equations =",
            audit.remaining_display_equations,
        )

        print(
            "private-use =",
            audit.private_use_characters,
        )

        print(
            "unknown types =",
            stats.unknown_block_types,
        )

        print(
            "mojibake =",
            audit.mojibake,
        )

        print(
            "Markdown =",
            markdown_path,
        )

        print(
            "QA =",
            qa_path,
        )


if __name__ == "__main__":
    main()
