import argparse
import json
from dataclasses import asdict

from lxml.etree import XMLSyntaxError

from paperflow.cleaners.elsevier_md import (
    clean_elsevier_markdown_file,
)
from paperflow.config import (
    load_settings,
    require_elsevier_api_key,
)
from paperflow.parsers.elsevier_xml import (
    convert_elsevier_xml_to_markdown,
    inspect_elsevier_xml,
)
from paperflow.sources.elsevier import (
    ElsevierClient,
    ElsevierError,
)
from paperflow.storage import build_paper_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live Elsevier PaperFlow smoke test.")

    parser.add_argument("doi")

    args = parser.parse_args()

    settings = load_settings()

    api_key = require_elsevier_api_key(settings)

    paths = build_paper_paths(args.doi)

    paths.ensure()

    qa = {
        "doi": paths.doi,
        "route": "elsevier",
        "metadata": {
            "status": "pending",
        },
        "xml": {
            "status": "pending",
        },
        "pdf": {
            "status": "pending",
        },
        "markdown": {
            "status": "pending",
        },
    }

    print()
    print(
        "DOI =",
        paths.doi,
    )

    print(
        "Paper directory =",
        paths.directory,
    )

    with ElsevierClient(
        api_key=api_key,
        timeout=settings.http_timeout,
    ) as client:
        # ----------------------------------
        # 1. Metadata
        # ----------------------------------

        print()
        print("[1/4] Fetching metadata...")

        metadata = client.fetch_metadata(paths.doi)

        paths.metadata_json.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        qa["metadata"] = {
            "status": "success",
        }

        print(
            "  saved:",
            paths.metadata_json,
        )

        # ----------------------------------
        # 2. XML
        # ----------------------------------

        print()
        print("[2/4] Fetching XML...")

        try:
            xml_content = client.fetch_xml(paths.doi)

            paths.xml.write_bytes(xml_content)

            xml_stats = inspect_elsevier_xml(xml_content)

            qa["xml"] = {
                "status": ("full_text" if xml_stats.is_full_text else "metadata_only"),
                "bytes": len(xml_content),
                **asdict(xml_stats),
            }

            print(
                "  sections =",
                xml_stats.section_count,
            )

            print(
                "  paragraphs =",
                xml_stats.paragraph_count,
            )

            print(
                "  references =",
                xml_stats.reference_count,
            )

            print(
                "  text characters =",
                xml_stats.text_characters,
            )

            print(
                "  full text =",
                xml_stats.is_full_text,
            )

            # ------------------------------
            # 3. XML -> raw Markdown
            #    -> cleaned Markdown
            # ------------------------------

            if xml_stats.is_full_text:
                print()
                print("[3/4] Converting XML to raw Markdown...")

                try:
                    raw_markdown = convert_elsevier_xml_to_markdown(
                        paths.xml,
                        paths.raw_md,
                    )

                    print(
                        "  raw Markdown saved:",
                        paths.raw_md,
                    )

                    print()
                    print("  Cleaning Markdown...")

                    markdown_stats = clean_elsevier_markdown_file(
                        paths.raw_md,
                        paths.xml,
                        paths.llm_md,
                    )

                    cleaned_markdown = paths.llm_md.read_text(encoding="utf-8")

                    warnings: list[str] = []

                    if markdown_stats.remaining_display_math != 0:
                        warnings.append("Display math remains after cleaning.")

                    if markdown_stats.missing_float_table_ids:
                        warnings.append("One or more XML float tables were not found in Markdown.")

                    markdown_status = "warning" if warnings else "success"

                    qa["markdown"] = {
                        "status": (markdown_status),
                        "source": ("elsevier_xml"),
                        "raw_file": (paths.raw_md.name),
                        "llm_file": (paths.llm_md.name),
                        "raw_characters": len(raw_markdown),
                        "characters": len(cleaned_markdown),
                        "warnings": warnings,
                        **asdict(markdown_stats),
                    }

                    print(
                        "  LLM Markdown saved:",
                        paths.llm_md,
                    )

                    print(
                        "  display equations removed =",
                        markdown_stats.display_equations_removed,
                    )

                    print(
                        "  remaining display math =",
                        markdown_stats.remaining_display_math,
                    )

                    print(
                        "  tables in Markdown =",
                        markdown_stats.table_count_markdown,
                    )

                    print(
                        "  references in Markdown =",
                        markdown_stats.reference_count_markdown,
                    )

                    print(
                        "  relocated tables =",
                        markdown_stats.relocated_table_ids,
                    )

                    print(
                        "  missing float tables =",
                        markdown_stats.missing_float_table_ids,
                    )

                    print(
                        "  has Results =",
                        markdown_stats.has_results,
                    )

                    print(
                        "  has Conclusion =",
                        markdown_stats.has_conclusion,
                    )

                    print(
                        "  has References =",
                        markdown_stats.has_references,
                    )

                except (
                    OSError,
                    UnicodeError,
                    ValueError,
                    XMLSyntaxError,
                ) as exc:
                    qa["markdown"] = {
                        "status": "error",
                        "source": ("elsevier_xml"),
                        "error": str(exc),
                    }

                    print(
                        "  MARKDOWN ERROR:",
                        exc,
                    )

            else:
                qa["markdown"] = {
                    "status": "not_created",
                    "reason": ("Elsevier XML did not contain structured full text."),
                }

                print()
                print("[3/4] XML is not full text; skipping Markdown.")

        except ElsevierError as exc:
            qa["xml"] = {
                "status": "error",
                "error": str(exc),
            }

            qa["markdown"] = {
                "status": "not_created",
                "reason": ("XML retrieval failed."),
            }

            print(
                "  XML ERROR:",
                exc,
            )

        # ----------------------------------
        # 4. PDF
        #
        # PDF full-text validation has not
        # been implemented yet.
        #
        # A file beginning with %PDF- is not
        # enough to prove that it is the
        # complete article.
        # ----------------------------------

        print()
        print("[4/4] Trying PDF...")

        try:
            pdf_content = client.fetch_pdf(paths.doi)

            paths.pdf.write_bytes(pdf_content)

            qa["pdf"] = {
                "status": ("downloaded_unvalidated"),
                "bytes": len(pdf_content),
                "validated": False,
            }

            print(
                "  PDF downloaded:",
                paths.pdf,
            )

            print("  NOTE: PDF has not yet been validated as full text.")

        except ElsevierError as exc:
            qa["pdf"] = {
                "status": "unavailable",
                "error": str(exc),
                "validated": False,
            }

            print(
                "  PDF unavailable:",
                exc,
            )

    # --------------------------------------
    # Overall status
    # --------------------------------------

    markdown_ok = qa["markdown"]["status"] in {
        "success",
        "warning",
    }

    pdf_downloaded = qa["pdf"]["status"] == "downloaded_unvalidated"

    if markdown_ok:
        overall = "pass"

    elif pdf_downloaded:
        overall = "needs_pdf_validation"

    else:
        overall = "no_full_text"

    qa["overall_status"] = overall

    paths.qa_json.write_text(
        json.dumps(
            qa,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "Overall status =",
        overall,
    )

    print()
    print(
        "QA saved:",
        paths.qa_json,
    )


if __name__ == "__main__":
    main()
