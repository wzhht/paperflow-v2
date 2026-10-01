from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from paperflow.config import ConfigError
from paperflow.parsers.mineru_pdf import MinerUError
from paperflow.pipeline import (
    PaperResult,
    PipelineError,
    process_doi,
)
from paperflow.sources.building_simulation_pdf import (
    BuildingSimulationPdfError,
)
from paperflow.sources.elsevier import ElsevierError
from paperflow.sources.nature_pdf import NaturePdfError


@dataclass(frozen=True)
class BatchItemResult:
    index: int
    doi: str
    route: str
    source: str
    status: str
    fallback_used: bool
    llm_markdown: str
    qa: str
    error: str


@dataclass(frozen=True)
class BatchRunResult:
    input_path: Path
    library_root: Path
    results_path: Path
    total: int
    success_count: int
    warning_count: int
    failed_count: int
    items: tuple[BatchItemResult, ...]


BatchResultCallback = Callable[
    [
        BatchItemResult,
        int,
    ],
    None,
]


_FIELDNAMES = (
    "index",
    "doi",
    "route",
    "source",
    "status",
    "fallback_used",
    "llm_markdown",
    "qa",
    "error",
)


_PROCESS_ERRORS = (
    BuildingSimulationPdfError,
    ConfigError,
    ElsevierError,
    MinerUError,
    NaturePdfError,
    OSError,
    PipelineError,
    ValueError,
)


def load_dois(
    input_path: str | Path,
) -> list[str]:
    """
    Load DOI values from a plain-text file.

    Rules:

    - one DOI per line
    - blank lines are ignored
    - lines beginning with # are ignored
    - surrounding whitespace is ignored
    - duplicate DOI values are processed only once
    """

    path = Path(input_path)

    if not path.is_file():
        raise FileNotFoundError(f"DOI input file does not exist: {path}")

    text = path.read_text(
        encoding="utf-8-sig",
    )

    dois: list[str] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        key = line.casefold()

        if key in seen:
            continue

        seen.add(key)
        dois.append(line)

    if not dois:
        raise ValueError(f"No DOI entries were found in: {path}")

    return dois


def _item_from_paper_result(
    index: int,
    result: PaperResult,
) -> BatchItemResult:
    return BatchItemResult(
        index=index,
        doi=result.doi,
        route=result.route,
        source=result.source,
        status=result.status,
        fallback_used=result.fallback_used,
        llm_markdown=(
            str(result.llm_markdown_path) if result.llm_markdown_path is not None else ""
        ),
        qa=str(result.qa_path),
        error="",
    )


def _item_from_error(
    index: int,
    doi: str,
    exc: Exception,
) -> BatchItemResult:
    return BatchItemResult(
        index=index,
        doi=doi,
        route="",
        source="",
        status="failed",
        fallback_used=False,
        llm_markdown="",
        qa="",
        error=(f"{type(exc).__name__}: {exc}"),
    )


def _write_results(
    items: list[BatchItemResult],
    results_path: Path,
) -> None:
    """
    Write the current batch manifest.

    This is called after every processed paper so completed results
    survive interruption of a long batch.
    """

    results_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with results_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=_FIELDNAMES,
        )

        writer.writeheader()

        for item in items:
            writer.writerow(
                {
                    "index": item.index,
                    "doi": item.doi,
                    "route": item.route,
                    "source": item.source,
                    "status": item.status,
                    "fallback_used": ("true" if item.fallback_used else "false"),
                    "llm_markdown": item.llm_markdown,
                    "qa": item.qa,
                    "error": item.error,
                }
            )


def run_batch(
    input_path: str | Path,
    *,
    library_root: str | Path,
    results_path: str | Path | None = None,
    on_result: BatchResultCallback | None = None,
) -> BatchRunResult:
    """
    Process all DOI values in one text file.

    Each DOI is passed through the normal process_doi() pipeline.

    Known acquisition, configuration, parsing, QA, and filesystem
    failures are captured in the batch manifest and do not stop the
    remaining papers.

    Unexpected programming errors are intentionally not swallowed.
    """

    input_path = Path(input_path)
    library_root = Path(library_root)

    dois = load_dois(input_path)

    library_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    if results_path is None:
        resolved_results_path = library_root / "batch_results.csv"
    else:
        resolved_results_path = Path(results_path)

    items: list[BatchItemResult] = []
    total = len(dois)

    for index, doi in enumerate(
        dois,
        start=1,
    ):
        try:
            result = process_doi(
                doi,
                library_root=library_root,
            )

            item = _item_from_paper_result(
                index,
                result,
            )

        except _PROCESS_ERRORS as exc:
            item = _item_from_error(
                index,
                doi,
                exc,
            )

        items.append(item)

        _write_results(
            items,
            resolved_results_path,
        )

        if on_result is not None:
            on_result(
                item,
                total,
            )

    success_count = sum(item.status == "success" for item in items)

    warning_count = sum(item.status == "warning" for item in items)

    failed_count = sum(item.status == "failed" for item in items)

    return BatchRunResult(
        input_path=input_path,
        library_root=library_root,
        results_path=resolved_results_path,
        total=total,
        success_count=success_count,
        warning_count=warning_count,
        failed_count=failed_count,
        items=tuple(items),
    )
