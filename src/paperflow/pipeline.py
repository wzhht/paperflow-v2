from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lxml.etree import XMLSyntaxError

from paperflow.cleaners.elsevier_md import (
    clean_elsevier_markdown_file,
)
from paperflow.config import (
    Settings,
    load_settings,
    require_elsevier_api_key,
    require_mineru_executable,
    require_springer_meta_api_key,
    require_springer_oa_api_key,
)
from paperflow.models import Route
from paperflow.parsers.elsevier_xml import (
    convert_elsevier_xml_to_markdown,
    inspect_elsevier_xml,
)
from paperflow.parsers.jats import (
    convert_jats_xml_to_markdown,
)
from paperflow.parsers.mineru_content import (
    convert_mineru_zip_to_markdown,
    load_mineru_structured_content_from_zip,
)
from paperflow.parsers.mineru_pdf import (
    parse_pdf_with_mineru,
)
from paperflow.qa.mineru import (
    audit_mineru_markdown,
)
from paperflow.qa.pdf import (
    validate_pdf_bytes,
)
from paperflow.qa.structured import (
    audit_jats_table_numeric_values,
    inspect_jats_xml,
)
from paperflow.recovery import (
    find_local_pdf,
    write_restricted_access_artifacts,
)
from paperflow.routing import route_doi
from paperflow.sources.building_simulation_pdf import (
    BuildingSimulationPdfClient,
    BuildingSimulationPdfContentError,
)
from paperflow.sources.elsevier import (
    ElsevierClient,
)
from paperflow.sources.nature_pdf import (
    NaturePdfClient,
    NaturePdfContentError,
)
from paperflow.sources.springer_nature import (
    SpringerNatureClient,
)
from paperflow.storage import (
    build_paper_paths,
)


class PipelineError(RuntimeError):
    """Base PaperFlow pipeline error."""


class UnsupportedRouteError(PipelineError):
    """The DOI does not have a supported PaperFlow V2 route."""


class PipelineContentError(PipelineError):
    """Acquired content failed PaperFlow scientific QA."""


class PdfInputRequiredError(PipelineError):
    """
    Retained for compatibility with earlier PaperFlow code.

    Building Simulation no longer requires --pdf because PaperFlow can
    attempt the publisher PDF automatically.
    """


@dataclass(frozen=True)
class PaperResult:
    doi: str
    route: str
    source: str
    status: str
    raw_markdown_path: Path | None
    llm_markdown_path: Path | None
    qa_path: Path
    fallback_used: bool = False


def process_doi(
    doi: str,
    *,
    pdf_path: str | Path | None = None,
    library_root: str | Path = "workspace/library",
    settings: Settings | None = None,
) -> PaperResult:
    """
    Process one DOI through PaperFlow V2.

    Supported routes:

    10.1016/...
        Elsevier structured XML
        -> semantic completeness validation
        -> litdown
        -> conservative Elsevier cleanup
        -> QA

    10.1038/...
        explicit --pdf, if supplied
        -> MinerU

        otherwise:

        Springer Nature JATS first
        -> if complete: JATS renderer + QA
        -> otherwise:
            exactly one local PDF in paper directory
            -> MinerU

        -> otherwise:
            public Nature PDF
            -> MinerU

        -> otherwise:
            partial Springer XML/metadata
            -> Markdown
            -> access.json recovery instructions
            -> warning

    10.1007/s12273...
        explicit --pdf, if supplied
        -> MinerU

        otherwise:

        exactly one local PDF in paper directory
        -> MinerU

        -> otherwise:
            public Springer PDF
            -> MinerU

        -> otherwise:
            partial Springer XML/metadata
            -> Markdown
            -> access.json recovery instructions
            -> warning
    """

    if settings is None:
        settings = load_settings()

    decision = route_doi(doi)

    if not decision.supported:
        raise UnsupportedRouteError(decision.reason)

    paths = build_paper_paths(
        decision.doi,
        library_root=library_root,
    )

    paths.ensure()

    if decision.route is Route.ELSEVIER:
        return _process_elsevier(
            paths,
            settings,
        )

    if decision.route is Route.NATURE:
        return _process_nature(
            paths,
            settings,
            pdf_path=pdf_path,
        )

    if decision.route is Route.BUILDING_SIMULATION:
        return _process_building_simulation(
            paths,
            settings,
            pdf_path=pdf_path,
        )

    raise UnsupportedRouteError(
        f"PaperFlow V2 route is recognized but not implemented: {decision.route.value}"
    )


def _process_elsevier(
    paths: Any,
    settings: Settings,
) -> PaperResult:
    """
    Elsevier primary structured route.

    Elsevier XML
    -> semantic full-text validation
    -> litdown raw Markdown
    -> conservative cleaner
    -> QA
    """

    api_key = require_elsevier_api_key(settings)

    with ElsevierClient(
        api_key=api_key,
        timeout=settings.http_timeout,
    ) as client:
        xml_content = client.fetch_xml(paths.doi)

    paths.xml.write_bytes(xml_content)

    xml_stats = inspect_elsevier_xml(xml_content)

    if not xml_stats.is_full_text:
        qa = {
            "doi": paths.doi,
            "route": (Route.ELSEVIER.value),
            "source": "elsevier_xml",
            "status": "failed",
            "fallback_used": False,
            "structured": (asdict(xml_stats)),
            "warnings": [],
            "failures": [("elsevier_xml_not_full_text")],
        }

        _write_json(
            paths.qa_json,
            qa,
        )

        raise PipelineContentError(
            f"Elsevier XML did not pass the structured full-text check: {xml_stats.reason}"
        )

    raw_markdown = convert_elsevier_xml_to_markdown(
        paths.xml,
        paths.raw_md,
    )

    markdown_stats = clean_elsevier_markdown_file(
        paths.raw_md,
        paths.xml,
        paths.llm_md,
    )

    final_markdown = paths.llm_md.read_text(encoding="utf-8")

    warnings: list[str] = []
    failures: list[str] = []

    if markdown_stats.remaining_display_math != 0:
        failures.append("display_math_remaining")

    if markdown_stats.missing_float_table_ids:
        failures.append("missing_float_tables")

    if markdown_stats.image_only_float_table_ids:
        warnings.append("image_only_tables")

    if xml_stats.reference_count > 0 and (
        markdown_stats.reference_count_markdown != xml_stats.reference_count
    ):
        warnings.append("reference_count_mismatch")

    if xml_stats.reference_count > 0 and not (markdown_stats.has_references):
        failures.append("references_missing")

    status = _status_from_checks(
        warnings=warnings,
        failures=failures,
    )

    qa = {
        "doi": paths.doi,
        "route": (Route.ELSEVIER.value),
        "source": "elsevier_xml",
        "status": status,
        "fallback_used": False,
        "structured": (asdict(xml_stats)),
        "markdown": {
            "raw_file": (paths.raw_md.name),
            "llm_file": (paths.llm_md.name),
            "raw_characters": len(raw_markdown),
            "final_characters": len(final_markdown),
            **asdict(markdown_stats),
        },
        "warnings": warnings,
        "failures": failures,
    }

    _write_json(
        paths.qa_json,
        qa,
    )

    if failures:
        raise PipelineContentError("Elsevier Markdown failed QA: " + ", ".join(failures))

    return PaperResult(
        doi=paths.doi,
        route=Route.ELSEVIER.value,
        source="elsevier_xml",
        status=status,
        raw_markdown_path=(paths.raw_md),
        llm_markdown_path=(paths.llm_md),
        qa_path=(paths.qa_json),
        fallback_used=False,
    )


def _process_nature(
    paths: Any,
    settings: Settings,
    *,
    pdf_path: str | Path | None = None,
) -> PaperResult:
    """
    Nature route.

    Priority:

    1. Explicit --pdf override.
    2. Complete Springer Nature JATS.
    3. Exactly one local PDF already in the paper directory.
    4. Public Nature PDF.
    5. Restricted-access partial XML/metadata Markdown.

    A local PDF placed into the paper directory may have any filename,
    as long as it is the only PDF in that directory.
    """

    #
    # Explicit --pdf is an intentional user override.
    #
    if pdf_path is not None:
        local_pdf = find_local_pdf(
            paths.directory,
            explicit_pdf=pdf_path,
        )

        return _process_pdf_with_mineru(
            paths,
            settings,
            pdf_content=None,
            route=Route.NATURE,
            source="local_pdf_mineru",
            fallback_used=True,
            fallback_reason=("Explicit local PDF supplied by user."),
            source_url=None,
            source_file=local_pdf,
        )

    #
    # Structured JATS is preferred when it is genuinely complete.
    #
    (
        jats_result,
        fallback_reason,
    ) = _try_process_nature_jats(
        paths,
        settings,
    )

    if jats_result is not None:
        return jats_result

    #
    # JATS was unavailable or incomplete.
    #
    # Check whether the user has manually placed exactly one PDF into
    # this paper directory.
    #
    local_pdf = find_local_pdf(paths.directory)

    if local_pdf is not None:
        return _process_pdf_with_mineru(
            paths,
            settings,
            pdf_content=None,
            route=Route.NATURE,
            source="local_pdf_mineru",
            fallback_used=True,
            fallback_reason=(
                fallback_reason or ("Structured Nature JATS unavailable; using local PDF.")
            ),
            source_url=None,
            source_file=local_pdf,
        )

    #
    # No local PDF exists.
    #
    # Try the publicly accessible Nature article PDF.
    #
    try:
        with NaturePdfClient(timeout=(settings.http_timeout)) as client:
            pdf_payload = client.fetch_pdf(paths.doi)

    except NaturePdfContentError as exc:
        #
        # Expected restricted-access case.
        #
        # For example, Nature redirects a .pdf request back to an HTML
        # article page because the current access context cannot obtain
        # the publisher PDF.
        #
        # Do not turn this into a failed paper. Save whatever structured
        # XML/metadata is available and leave a recovery instruction.
        #
        return _process_springer_restricted_partial(
            paths,
            settings,
            route=Route.NATURE,
            reason=str(exc),
            fallback_reason=(fallback_reason),
        )

    return _process_pdf_with_mineru(
        paths,
        settings,
        pdf_content=(pdf_payload.content),
        route=Route.NATURE,
        source="nature_pdf_mineru",
        fallback_used=True,
        fallback_reason=(fallback_reason),
        source_url=(pdf_payload.url),
        source_file=None,
    )


def _try_process_nature_jats(
    paths: Any,
    settings: Settings,
) -> tuple[
    PaperResult | None,
    str | None,
]:
    """
    Attempt the preferred Nature JATS route.

    Returns:

        (PaperResult, None)
            if JATS succeeds.

        (None, reason)
            if the pipeline should fall back to PDF.

    JATS failure itself is not fatal for Nature because PDF is a
    validated fallback route.
    """

    try:
        api_key = require_springer_oa_api_key(settings)

        client = SpringerNatureClient(
            api_key,
            settings.http_timeout,
        )

        try:
            payload = client.fetch_jats(paths.doi)

        finally:
            client.close()

    except (
        RuntimeError,
        ValueError,
        OSError,
        UnicodeError,
        XMLSyntaxError,
    ) as exc:
        return (
            None,
            (f"jats_unavailable: {type(exc).__name__}: {exc}"),
        )

    response_path = paths.directory / "springer_oa_response.xml"

    response_path.write_bytes(payload.response_xml)

    paths.jats_xml.write_bytes(payload.article_xml)

    try:
        stats = inspect_jats_xml(paths.jats_xml)

    except (
        RuntimeError,
        ValueError,
        OSError,
        UnicodeError,
        XMLSyntaxError,
    ) as exc:
        return (
            None,
            (f"jats_validation_failed: {type(exc).__name__}: {exc}"),
        )

    if not stats.candidate_full_text:
        return (
            None,
            "jats_not_full_text",
        )

    try:
        markdown = convert_jats_xml_to_markdown(
            paths.jats_xml,
            paths.llm_md,
        )

        table_audit = audit_jats_table_numeric_values(
            paths.jats_xml,
            markdown,
        )

    except (
        RuntimeError,
        ValueError,
        OSError,
        UnicodeError,
        XMLSyntaxError,
    ) as exc:
        return (
            None,
            (f"jats_render_failed: {type(exc).__name__}: {exc}"),
        )

    if stats.table_count > 0 and not table_audit.values_match:
        return (
            None,
            ("jats_table_numeric_values_mismatch"),
        )

    warnings: list[str] = []

    if stats.reference_count <= 0:
        warnings.append("references_not_detected")

    status = _status_from_checks(
        warnings=warnings,
        failures=[],
    )

    qa = {
        "doi": paths.doi,
        "route": (Route.NATURE.value),
        "source": ("springer_nature_jats"),
        "status": status,
        "fallback_used": False,
        "source_response": {
            "article_count": (payload.article_count),
            "response_file": (response_path.name),
            "jats_file": (paths.jats_xml.name),
        },
        "structured": (asdict(stats)),
        "table_numeric_audit": (asdict(table_audit)),
        "markdown": {
            "llm_file": (paths.llm_md.name),
            "characters": len(markdown),
        },
        "warnings": warnings,
        "failures": [],
    }

    _write_json(
        paths.qa_json,
        qa,
    )

    return (
        PaperResult(
            doi=paths.doi,
            route=(Route.NATURE.value),
            source=("springer_nature_jats"),
            status=status,
            raw_markdown_path=None,
            llm_markdown_path=(paths.llm_md),
            qa_path=(paths.qa_json),
            fallback_used=False,
        ),
        None,
    )


def _process_building_simulation(
    paths: Any,
    settings: Settings,
    *,
    pdf_path: str | Path | None,
) -> PaperResult:
    """
    Building Simulation route.

    Priority:

    1. Explicit --pdf override.
    2. Exactly one PDF already present in the paper directory.
    3. Public Springer article PDF.
    4. Restricted-access partial Springer XML/metadata result.

    A manually supplied PDF in the paper directory may use any
    filename. If more than one PDF exists, find_local_pdf() refuses
    to guess and asks the user to use --pdf.
    """

    #
    # Explicit --pdf, or exactly one local PDF already placed in the
    # paper directory.
    #
    local_pdf = find_local_pdf(
        paths.directory,
        explicit_pdf=pdf_path,
    )

    if local_pdf is not None:
        return _process_pdf_with_mineru(
            paths,
            settings,
            pdf_content=None,
            route=(Route.BUILDING_SIMULATION),
            source="local_pdf_mineru",
            fallback_used=False,
            fallback_reason=None,
            source_url=None,
            source_file=local_pdf,
        )

    #
    # No local PDF.
    #
    # Try the publisher PDF.
    #
    try:
        with BuildingSimulationPdfClient(settings.http_timeout) as client:
            payload = client.fetch_pdf(paths.doi)

    except BuildingSimulationPdfContentError as exc:
        return _process_springer_restricted_partial(
            paths,
            settings,
            route=(Route.BUILDING_SIMULATION),
            reason=str(exc),
            fallback_reason=("building_simulation_pdf_unavailable"),
        )

    return _process_pdf_with_mineru(
        paths,
        settings,
        pdf_content=(payload.content),
        route=(Route.BUILDING_SIMULATION),
        source=("building_simulation_pdf_mineru"),
        fallback_used=False,
        fallback_reason=None,
        source_url=payload.url,
        source_file=None,
    )


def _process_springer_restricted_partial(
    paths: Any,
    settings: Settings,
    *,
    route: Route,
    reason: str,
    fallback_reason: str | None,
) -> PaperResult:
    """
    Produce a recoverable partial result when Springer/Nature full text
    is not available through the current API/public PDF access.

    The partial result is a warning, not a hard failure.

    PaperFlow:

    - preserves any partial JATS XML already acquired;
    - otherwise attempts Springer Metadata PAM XML;
    - converts available structured metadata/abstract to Markdown;
    - writes access.json with recovery instructions;
    - tells the user to place exactly one PDF in the paper directory;
    - accepts any PDF filename;
    - the same `paperflow process` command can then be rerun.
    """

    existing_xml_path = None

    if route is Route.NATURE and paths.jats_xml.is_file():
        existing_xml_path = paths.jats_xml

    access_reason_parts = []

    if fallback_reason:
        access_reason_parts.append(fallback_reason)

    if reason:
        access_reason_parts.append(reason)

    access_reason = "; ".join(access_reason_parts)

    write_restricted_access_artifacts(
        paths.doi,
        route=route.value,
        paper_directory=(paths.directory),
        raw_markdown_path=(paths.raw_md),
        llm_markdown_path=(paths.llm_md),
        qa_path=(paths.qa_json),
        library_root=(paths.directory.parent),
        api_key=require_springer_meta_api_key(settings),
        timeout=(settings.http_timeout),
        reason=access_reason,
        existing_xml_path=(existing_xml_path),
    )

    return PaperResult(
        doi=paths.doi,
        route=route.value,
        source=("springer_restricted_partial"),
        status="warning",
        raw_markdown_path=(paths.raw_md),
        llm_markdown_path=(paths.llm_md),
        qa_path=(paths.qa_json),
        fallback_used=True,
    )


def _process_pdf_with_mineru(
    paths: Any,
    settings: Settings,
    *,
    pdf_content: bytes | None,
    route: Route,
    source: str,
    fallback_used: bool,
    fallback_reason: str | None,
    source_url: str | None,
    source_file: str | Path | None,
) -> PaperResult:
    """
    Shared PDF -> MinerU route.

    Used by:

    - Building Simulation publisher PDF
    - Building Simulation local PDF
    - Nature public PDF fallback
    - Nature local PDF recovery

    Local PDF rules:

    - --pdf may point anywhere.
    - If exactly one PDF is already in the paper directory, it may use
      any filename.
    - A local PDF inside the paper directory is processed in place.
      PaperFlow does NOT create a duplicate paper.pdf beside it.
    - An external explicit --pdf is copied into the paper directory as
      paper.pdf so that PaperFlow retains the input artifact.
    """

    source_path: Path | None = None

    if source_file is not None:
        source_path = Path(source_file)

        if not source_path.is_file():
            raise FileNotFoundError(f"Local PDF does not exist: {source_path}")

        if source_path.suffix.lower() != ".pdf":
            raise ValueError(f"Local PDF input must have a .pdf extension: {source_path}")

        if pdf_content is None:
            pdf_content = source_path.read_bytes()

    if pdf_content is None:
        raise PipelineContentError(
            "PDF processing was requested but no PDF bytes or local PDF file were supplied."
        )

    pdf_validation = validate_pdf_bytes(pdf_content)

    #
    # validate_pdf_bytes() intentionally returns "candidate"
    # when no trusted expected page count exists.
    #
    # For locally supplied Building Simulation PDFs and Nature
    # PDFs acquired directly from the publisher article URL, we
    # accept the document if:
    #
    # - PDF signature exists
    # - pypdf can parse it
    # - page count is positive
    #
    pdf_acceptable = (
        pdf_validation.signature_ok
        and pdf_validation.parseable
        and (pdf_validation.actual_pages is not None)
        and (pdf_validation.actual_pages > 0)
    )

    if not pdf_acceptable:
        qa = {
            "doi": paths.doi,
            "route": route.value,
            "source": source,
            "status": "failed",
            "fallback_used": (fallback_used),
            "fallback_reason": (fallback_reason),
            "pdf": {
                **asdict(pdf_validation),
                "source_file": (str(source_path) if source_path is not None else None),
                "source_url": (source_url),
            },
            "warnings": [],
            "failures": ["pdf_not_parseable"],
        }

        _write_json(
            paths.qa_json,
            qa,
        )

        raise PipelineContentError(f"PDF failed basic validation: {pdf_validation.reason}")

    #
    # Decide which PDF MinerU should actually read.
    #
    # Publisher-downloaded bytes:
    #     save as canonical paper.pdf.
    #
    # Local file already inside paper directory:
    #     process it directly under its existing filename.
    #
    # Explicit local file outside paper directory:
    #     copy it to canonical paper.pdf.
    #
    if source_path is None:
        paths.pdf.write_bytes(pdf_content)

        working_pdf = paths.pdf

    elif _is_file_inside_directory(
        source_path,
        paths.directory,
    ):
        working_pdf = source_path

    else:
        paths.pdf.write_bytes(pdf_content)

        working_pdf = paths.pdf

    executable = require_mineru_executable(settings)

    mineru_zip = paths.directory / "mineru.zip"

    parse_result = parse_pdf_with_mineru(
        working_pdf,
        mineru_zip,
        executable=executable,
        tier=settings.mineru_tier,
    )

    structured = load_mineru_structured_content_from_zip(mineru_zip)

    structured_path = paths.directory / "structured_content.json"

    structured_path.write_text(
        json.dumps(
            structured,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (
        markdown,
        render_stats,
    ) = convert_mineru_zip_to_markdown(
        mineru_zip,
        paths.llm_md,
    )

    audit = audit_mineru_markdown(
        structured,
        markdown,
    )

    warnings: list[str] = []
    failures: list[str] = []

    #
    # Hard failures
    #

    if not audit.table_content_exact_match:
        failures.append("table_content_mismatch")

    if not audit.table_numeric_values_match:
        failures.append("table_numeric_values_mismatch")

    if not audit.has_references:
        failures.append("references_missing")

    if audit.remaining_images:
        failures.append("remaining_images")

    if audit.remaining_base64:
        failures.append("remaining_base64")

    if audit.remaining_display_equations:
        failures.append("remaining_display_equations")

    if audit.mojibake:
        failures.append("mojibake")

    #
    # Warnings only
    #

    if audit.private_use_characters > 0:
        warnings.append("private_use_characters")

    if render_stats.unknown_block_types:
        warnings.append("unknown_block_types")

    if structured.get("is_full_document") is False:
        warnings.append("mineru_not_marked_full_document")

    status = _status_from_checks(
        warnings=warnings,
        failures=failures,
    )

    qa = {
        "doi": paths.doi,
        "route": route.value,
        "source": source,
        "status": status,
        "fallback_used": (fallback_used),
        "fallback_reason": (fallback_reason),
        "pdf": {
            **asdict(pdf_validation),
            "source_file": (str(source_path) if source_path is not None else None),
            "source_url": (source_url),
            "working_file": (working_pdf.name),
            "working_path": (str(working_pdf)),
            "accepted_input": (pdf_acceptable),
        },
        "mineru": {
            "tier": (settings.mineru_tier),
            "zip_file": (mineru_zip.name),
            "structured_file": (structured_path.name),
            "artifact_names": list(parse_result.artifact_names),
            "is_full_document": (structured.get("is_full_document")),
        },
        "render": (asdict(render_stats)),
        "audit": (asdict(audit)),
        "warnings": warnings,
        "failures": failures,
    }

    _write_json(
        paths.qa_json,
        qa,
    )

    if failures:
        raise PipelineContentError("MinerU Markdown failed QA: " + ", ".join(failures))

    #
    # If this paper previously had a restricted-access access.json,
    # retain that log but mark the paper as recovered successfully
    # using a local/public PDF.
    #
    _mark_access_recovered(
        paths,
        working_pdf=working_pdf,
        source=source,
    )

    return PaperResult(
        doi=paths.doi,
        route=route.value,
        source=source,
        status=status,
        raw_markdown_path=None,
        llm_markdown_path=(paths.llm_md),
        qa_path=(paths.qa_json),
        fallback_used=(fallback_used),
    )


def _is_file_inside_directory(
    file_path: str | Path,
    directory: str | Path,
) -> bool:
    """
    Return True when file_path is directly inside directory.

    PaperFlow only auto-discovers PDFs directly inside the paper
    directory, not recursively inside subdirectories.
    """

    file_path = Path(file_path)

    directory = Path(directory)

    try:
        return file_path.resolve().parent == directory.resolve()

    except OSError:
        return False


def _mark_access_recovered(
    paths: Any,
    *,
    working_pdf: Path,
    source: str,
) -> None:
    """
    Update an existing access.json after a previously restricted paper
    has successfully been recovered through a PDF.

    The log is retained rather than deleted so there is a record of the
    original restricted-access condition.
    """

    access_path = paths.directory / "access.json"

    if not access_path.is_file():
        return

    payload: dict[str, Any]

    try:
        loaded = json.loads(access_path.read_text(encoding="utf-8"))

        if isinstance(
            loaded,
            dict,
        ):
            payload = loaded
        else:
            payload = {}

    except (
        OSError,
        ValueError,
        TypeError,
    ):
        payload = {}

    payload.update(
        {
            "doi": paths.doi,
            "status": ("recovered_with_pdf"),
            "full_text_available": True,
            "recovered_source": source,
            "recovered_pdf": str(working_pdf),
            "recovery_note": (
                "PaperFlow successfully processed a PDF through the MinerU pipeline."
            ),
        }
    )

    _write_json(
        access_path,
        payload,
    )


def _status_from_checks(
    *,
    warnings: list[str],
    failures: list[str],
) -> str:
    if failures:
        return "failed"

    if warnings:
        return "warning"

    return "success"


def _write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
