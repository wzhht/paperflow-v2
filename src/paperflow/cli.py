from __future__ import annotations

from importlib.metadata import (
    PackageNotFoundError,
)
from importlib.metadata import (
    version as package_version,
)
from pathlib import Path
from typing import Annotated

import typer

from paperflow.batch import (
    BatchItemResult,
    run_batch,
)
from paperflow.config import ConfigError
from paperflow.parsers.mineru_pdf import (
    MinerUError,
)
from paperflow.pipeline import (
    PaperResult,
    PipelineError,
    process_doi,
)
from paperflow.sources.building_simulation_pdf import (
    BuildingSimulationPdfError,
)
from paperflow.sources.elsevier import (
    ElsevierError,
)
from paperflow.sources.nature_pdf import (
    NaturePdfError,
)

DEFAULT_LIBRARY_ROOT = Path(
    "workspace/library"
)


app = typer.Typer(
    name="paperflow",
    help=(
        "Academic paper acquisition "
        "and LLM-ready conversion pipeline."
    ),
    no_args_is_help=True,
)


def _get_version() -> str:
    try:
        return package_version(
            "paperflow"
        )

    except PackageNotFoundError:
        return "unknown"


def _display_result(
    result: PaperResult,
) -> None:
    typer.echo()

    typer.echo(
        f"DOI = {result.doi}"
    )

    typer.echo(
        f"Route = {result.route}"
    )

    typer.echo(
        f"Source = {result.source}"
    )

    typer.echo(
        f"Status = {result.status}"
    )

    typer.echo(
        "Fallback used = "
        + (
            "yes"
            if result.fallback_used
            else "no"
        )
    )

    if (
        result.raw_markdown_path
        is not None
    ):
        typer.echo(
            "Raw Markdown = "
            f"{result.raw_markdown_path}"
        )

    if (
        result.llm_markdown_path
        is not None
    ):
        typer.echo(
            "LLM Markdown = "
            f"{result.llm_markdown_path}"
        )

    typer.echo(
        f"QA = {result.qa_path}"
    )

    if (
        result.source
        == "springer_restricted_partial"
    ):
        paper_directory = (
            result.qa_path.parent
        )

        library_root = (
            paper_directory.parent
        )

        typer.echo()

        typer.echo(
            "Access = restricted / "
            "public full text unavailable"
        )

        typer.echo(
            "Partial XML/metadata "
            "Markdown was saved."
        )

        typer.echo()

        typer.echo(
            "If you legally obtain "
            "the main article PDF:"
        )

        typer.echo(
            "Place exactly ONE PDF "
            "file in:"
        )

        typer.echo(
            f"  {paper_directory}"
        )

        typer.echo(
            "The PDF filename can "
            "be anything."
        )

        typer.echo()

        typer.echo(
            "Then rerun:"
        )

        typer.echo(
            "  paperflow process "
            f"{result.doi} "
            "--library-root "
            f'"{library_root}"'
        )


def _display_batch_item(
    item: BatchItemResult,
    total: int,
) -> None:
    prefix = (
        f"[{item.index}/{total}] "
        f"{item.doi}"
    )

    if item.status == "failed":
        typer.echo(
            f"{prefix} -> FAILED"
        )

        typer.echo(
            f"    {item.error}"
        )

        return

    if (
        item.source
        == "springer_restricted_partial"
    ):
        typer.echo(
            f"{prefix} -> warning "
            "(restricted access; "
            "partial XML/metadata)"
        )

        return

    typer.echo(
        f"{prefix} "
        f"-> {item.status} "
        f"({item.source})"
    )


@app.callback()
def main() -> None:
    """PaperFlow command line interface."""


@app.command()
def version() -> None:
    """Show PaperFlow version."""

    typer.echo(
        "PaperFlow "
        f"{_get_version()}"
    )


@app.command("process")
def process_command(
    doi: Annotated[
        str,
        typer.Argument(
            help="DOI to process.",
        ),
    ],
    pdf: Annotated[
        Path | None,
        typer.Option(
            "--pdf",
            help=(
                "Optional local PDF "
                "override for PDF-based "
                "routes."
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ] = None,
    library_root: Annotated[
        Path,
        typer.Option(
            "--library-root",
            help=(
                "PaperFlow library "
                "output directory."
            ),
            file_okay=False,
            dir_okay=True,
            resolve_path=False,
        ),
    ] = DEFAULT_LIBRARY_ROOT,
) -> None:
    """
    Process one DOI.
    """

    try:
        result = process_doi(
            doi,
            pdf_path=pdf,
            library_root=library_root,
        )

    except (
        BuildingSimulationPdfError,
        ConfigError,
        ElsevierError,
        MinerUError,
        NaturePdfError,
        OSError,
        PipelineError,
        ValueError,
    ) as exc:
        typer.echo(
            "ERROR: "
            f"{type(exc).__name__}: "
            f"{exc}",
            err=True,
        )

        raise typer.Exit(
            code=1
        ) from exc

    _display_result(
        result
    )


@app.command("process-list")
def process_list_command(
    input_file: Annotated[
        Path,
        typer.Argument(
            help=(
                "Text file containing "
                "one DOI per line."
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    library_root: Annotated[
        Path,
        typer.Option(
            "--library-root",
            help=(
                "Directory containing "
                "the per-paper output "
                "directories."
            ),
            file_okay=False,
            dir_okay=True,
            resolve_path=False,
        ),
    ] = DEFAULT_LIBRARY_ROOT,
    results: Annotated[
        Path | None,
        typer.Option(
            "--results",
            help=(
                "Optional batch result "
                "CSV path. Defaults to "
                "<library-root>/"
                "batch_results.csv."
            ),
            file_okay=True,
            dir_okay=False,
            resolve_path=False,
        ),
    ] = None,
) -> None:
    """
    Process a text file containing one DOI per line.
    """

    typer.echo(
        f"Input = {input_file}"
    )

    typer.echo(
        "Library root = "
        f"{library_root}"
    )

    typer.echo()

    try:
        result = run_batch(
            input_file,
            library_root=library_root,
            results_path=results,
            on_result=(
                _display_batch_item
            ),
        )

    except (
        OSError,
        ValueError,
    ) as exc:
        typer.echo(
            "ERROR: "
            f"{type(exc).__name__}: "
            f"{exc}",
            err=True,
        )

        raise typer.Exit(
            code=1
        ) from exc

    typer.echo()

    typer.echo(
        "Batch complete"
    )

    typer.echo(
        f"Total = {result.total}"
    )

    typer.echo(
        "Success = "
        f"{result.success_count}"
    )

    typer.echo(
        "Warning = "
        f"{result.warning_count}"
    )

    typer.echo(
        "Failed = "
        f"{result.failed_count}"
    )

    typer.echo(
        "Results = "
        f"{result.results_path}"
    )


if __name__ == "__main__":
    app()