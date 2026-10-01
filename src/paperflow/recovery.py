from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx
from lxml import etree

from paperflow.utils.doi import normalize_doi

SPRINGER_META_V2_API = "https://api.springernature.com/meta/v2/json"


class MultipleLocalPdfError(ValueError):
    """More than one local PDF was found for one paper."""


class SpringerMetadataRecoveryError(RuntimeError):
    """Springer metadata recovery failed."""


@dataclass(frozen=True)
class RestrictedAccessArtifacts:
    markdown_path: Path
    raw_markdown_path: Path
    qa_path: Path
    access_json_path: Path
    partial_xml_path: Path | None
    metadata_json_path: Path | None
    metadata_error: str | None


def find_local_pdf(
    paper_directory: str | Path,
    *,
    explicit_pdf: str | Path | None = None,
) -> Path | None:
    """
    Resolve a local article PDF.

    Priority:

    1. Explicit --pdf.
    2. Exactly one PDF directly inside the paper directory.
    3. None if no local PDF exists.

    If multiple PDFs exist, PaperFlow refuses to guess.
    """

    paper_directory = Path(paper_directory)

    if explicit_pdf is not None:
        explicit_path = Path(explicit_pdf)

        if not explicit_path.is_file():
            raise FileNotFoundError(f"Explicit PDF does not exist: {explicit_path}")

        if explicit_path.suffix.lower() != ".pdf":
            raise ValueError(f"Explicit --pdf file must have a .pdf extension: {explicit_path}")

        return explicit_path

    if not paper_directory.is_dir():
        return None

    candidates = sorted(
        (
            path
            for path in paper_directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        ),
        key=lambda path: path.name.casefold(),
    )

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    names = "\n".join(f"- {path.name}" for path in candidates)

    raise MultipleLocalPdfError(
        "Multiple local PDF files were found in the paper directory. "
        "PaperFlow will not guess which one is the main article.\n"
        f"{names}\n"
        "Use --pdf to explicitly select the main article PDF."
    )


def _safe_xml_root(
    content: bytes,
) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        recover=False,
        huge_tree=True,
    )

    try:
        return etree.fromstring(
            content,
            parser=parser,
        )

    except etree.XMLSyntaxError as exc:
        raise SpringerMetadataRecoveryError("Springer recovery XML is not valid XML.") from exc


def _node_text(
    node: etree._Element,
) -> str:
    return " ".join(part.strip() for part in node.itertext() if part.strip())


def _first_text(
    root: etree._Element,
    names: tuple[str, ...],
) -> str | None:
    for name in names:
        nodes = root.xpath(f".//*[local-name()='{name}']")

        for node in nodes:
            text = _node_text(node)

            if text:
                return text

    return None


def _all_text(
    root: etree._Element,
    names: tuple[str, ...],
) -> tuple[str, ...]:
    values: list[str] = []

    for name in names:
        nodes = root.xpath(f".//*[local-name()='{name}']")

        for node in nodes:
            text = _node_text(node)

            if text and text not in values:
                values.append(text)

    return tuple(values)


def _normalize_possible_doi(
    value: str,
) -> str | None:
    text = value.strip()

    if text.lower().startswith("doi:"):
        text = text[4:].strip()

    try:
        return normalize_doi(text)

    except ValueError:
        return None


def _xml_contains_doi(
    content: bytes,
    doi: str,
) -> bool:
    root = _safe_xml_root(content)

    expected = normalize_doi(doi)

    nodes = root.xpath(
        ".//*[local-name()='doi' or local-name()='identifier' or local-name()='article-id']"
    )

    for node in nodes:
        text = _node_text(node)

        normalized = _normalize_possible_doi(text)

        if normalized == expected:
            return True

    return False


def _extract_authors(
    root: etree._Element,
) -> tuple[str, ...]:
    authors: list[str] = []

    for node in root.xpath(".//*[local-name()='creator']"):
        text = _node_text(node)

        if text and text not in authors:
            authors.append(text)

    if authors:
        return tuple(authors)

    contributors = root.xpath(".//*[local-name()='contrib']")

    for contributor in contributors:
        contrib_type = (contributor.get("contrib-type") or "").lower()

        if contrib_type and contrib_type != "author":
            continue

        surname = _first_text(
            contributor,
            ("surname",),
        )

        given = _first_text(
            contributor,
            (
                "given-names",
                "givenName",
                "firstName",
            ),
        )

        if surname and given:
            name = f"{given} {surname}"

        elif surname:
            name = surname

        elif given:
            name = given

        else:
            name = _node_text(contributor)

        if name and name not in authors:
            authors.append(name)

    return tuple(authors)


def _extract_publication_date(
    root: etree._Element,
) -> str | None:
    direct = _first_text(
        root,
        (
            "publicationDate",
            "publication-date",
        ),
    )

    if direct:
        return direct

    pub_dates = root.xpath(".//*[local-name()='pub-date']")

    for node in pub_dates:
        year = _first_text(
            node,
            ("year",),
        )

        month = _first_text(
            node,
            ("month",),
        )

        day = _first_text(
            node,
            ("day",),
        )

        parts = [
            part
            for part in (
                year,
                month,
                day,
            )
            if part
        ]

        if parts:
            return "-".join(parts)

    return _first_text(
        root,
        ("year",),
    )


def _extract_pages(
    root: etree._Element,
) -> str | None:
    first_page = _first_text(
        root,
        (
            "fpage",
            "startingPage",
            "startPage",
        ),
    )

    last_page = _first_text(
        root,
        (
            "lpage",
            "endingPage",
            "endPage",
        ),
    )

    if first_page and last_page:
        if first_page == last_page:
            return first_page

        return f"{first_page}-{last_page}"

    return first_page or last_page


def _extract_publisher_url(
    root: etree._Element,
) -> str | None:
    url_nodes = root.xpath(".//*[local-name()='url']")

    for node in url_nodes:
        value_nodes = node.xpath(".//*[local-name()='value']")

        for value_node in value_nodes:
            text = _node_text(value_node)

            if text.startswith(
                (
                    "http://",
                    "https://",
                )
            ):
                return text

        text = _node_text(node)

        if text.startswith(
            (
                "http://",
                "https://",
            )
        ):
            return text

    self_uri_nodes = root.xpath(".//*[local-name()='self-uri']")

    for node in self_uri_nodes:
        for key, value in node.attrib.items():
            if (key.endswith("}href") or key == "href") and value.startswith(
                (
                    "http://",
                    "https://",
                )
            ):
                return value

    return None


def _extract_partial_fields(
    content: bytes,
) -> dict[str, object]:
    root = _safe_xml_root(content)

    return {
        "title": _first_text(
            root,
            (
                "article-title",
                "title",
            ),
        ),
        "authors": _extract_authors(root),
        "journal": _first_text(
            root,
            (
                "journal-title",
                "publicationName",
                "publication-name",
                "journalTitle",
            ),
        ),
        "publication_date": (_extract_publication_date(root)),
        "volume": _first_text(
            root,
            (
                "volume",
                "volumeId",
            ),
        ),
        "issue": _first_text(
            root,
            (
                "issue",
                "issueId",
                "number",
            ),
        ),
        "pages": _extract_pages(root),
        "publisher": _first_text(
            root,
            (
                "publisher-name",
                "publisher",
            ),
        ),
        "abstract": _first_text(
            root,
            (
                "abstract",
                "description",
            ),
        ),
        "keywords": _all_text(
            root,
            (
                "kwd",
                "keyword",
            ),
        ),
        "open_access": _first_text(
            root,
            (
                "openAccess",
                "open-access",
            ),
        ),
        "copyright": _first_text(
            root,
            (
                "copyright-statement",
                "copyright",
                "license-p",
            ),
        ),
        "url": _extract_publisher_url(root),
    }


def _meta_record_doi(
    record: dict[str, object],
) -> str | None:
    for key in (
        "doi",
        "identifier",
    ):
        value = record.get(key)

        if not isinstance(
            value,
            str,
        ):
            continue

        normalized = _normalize_possible_doi(value)

        if normalized:
            return normalized

    return None


def _select_exact_meta_record(
    payload: dict[str, object],
    doi: str,
) -> dict[str, object]:
    normalized = normalize_doi(doi)

    records = payload.get("records")

    if not isinstance(
        records,
        list,
    ):
        raise SpringerMetadataRecoveryError(
            "Springer Meta v2 response did not contain a records list."
        )

    for record in records:
        if not isinstance(
            record,
            dict,
        ):
            continue

        record_doi = _meta_record_doi(record)

        if record_doi == normalized:
            return record

    raise SpringerMetadataRecoveryError(
        f"Springer Meta v2 response did not contain the exact DOI {normalized}."
    )


def _fetch_meta_v2_record(
    doi: str,
    *,
    api_key: str,
    timeout: float,
) -> tuple[
    dict[str, object],
    dict[str, object],
]:
    normalized = normalize_doi(doi)

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": ("PaperFlow/0.2.0 (academic paper processing)"),
                "Accept": "application/json",
            },
        ) as client:
            response = client.get(
                SPRINGER_META_V2_API,
                params={
                    "q": f"doi:{normalized}",
                    "api_key": api_key,
                    "p": "1",
                },
            )

    except httpx.RequestError as exc:
        raise SpringerMetadataRecoveryError(
            f"Springer Meta v2 request failed: {type(exc).__name__}: {exc}"
        ) from exc

    if response.is_error:
        raise SpringerMetadataRecoveryError(
            f"Springer Meta v2 returned HTTP {response.status_code}."
        )

    try:
        payload = response.json()

    except ValueError as exc:
        raise SpringerMetadataRecoveryError("Springer Meta v2 did not return valid JSON.") from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise SpringerMetadataRecoveryError(
            "Springer Meta v2 returned an unexpected JSON structure."
        )

    record = _select_exact_meta_record(
        payload,
        normalized,
    )

    return (
        payload,
        record,
    )


def _meta_text(
    record: dict[str, object],
    *keys: str,
) -> str | None:
    for key in keys:
        value = record.get(key)

        if not isinstance(
            value,
            str,
        ):
            continue

        text = value.strip()

        if text:
            return text

    return None


def _meta_scalar_text(
    record: dict[str, object],
    *keys: str,
) -> str | None:
    for key in keys:
        value = record.get(key)

        if isinstance(
            value,
            str,
        ):
            text = value.strip()

            if text:
                return text

        elif isinstance(
            value,
            bool,
        ):
            return "true" if value else "false"

        elif isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            return str(value)

    return None


def _meta_authors(
    record: dict[str, object],
) -> tuple[str, ...]:
    creators = record.get("creators")

    if creators is None:
        creators = record.get("authors")

    if isinstance(
        creators,
        str,
    ):
        text = creators.strip()

        return (text,) if text else ()

    if not isinstance(
        creators,
        list,
    ):
        return ()

    authors: list[str] = []

    for creator_item in creators:
        value: object | None

        if isinstance(
            creator_item,
            str,
        ):
            value = creator_item

        elif isinstance(
            creator_item,
            dict,
        ):
            value = (
                creator_item.get("creator")
                or creator_item.get("name")
                or creator_item.get("author")
            )

        else:
            continue

        if not isinstance(
            value,
            str,
        ):
            continue

        name = value.strip()

        if name and name not in authors:
            authors.append(name)

    return tuple(authors)


def _meta_keywords(
    record: dict[str, object],
) -> tuple[str, ...]:
    value = record.get("keyword")

    if value is None:
        value = record.get("keywords")

    if isinstance(
        value,
        str,
    ):
        text = value.strip()

        return (text,) if text else ()

    if not isinstance(
        value,
        list,
    ):
        return ()

    keywords: list[str] = []

    for item in value:
        text: str | None = None

        if isinstance(
            item,
            str,
        ):
            text = item.strip()

        elif isinstance(
            item,
            dict,
        ):
            possible = item.get("keyword") or item.get("value") or item.get("subject")

            if isinstance(
                possible,
                str,
            ):
                text = possible.strip()

        if text and text not in keywords:
            keywords.append(text)

    return tuple(keywords)


def _meta_pages(
    record: dict[str, object],
) -> str | None:
    first_page = _meta_text(
        record,
        "startingPage",
        "startPage",
        "firstPage",
    )

    last_page = _meta_text(
        record,
        "endingPage",
        "endPage",
        "lastPage",
    )

    if first_page and last_page:
        if first_page == last_page:
            return first_page

        return f"{first_page}-{last_page}"

    return first_page or last_page


def _meta_url(
    record: dict[str, object],
) -> str | None:
    urls = record.get("url")

    if isinstance(
        urls,
        str,
    ):
        value = urls.strip()

        if value.startswith(
            (
                "http://",
                "https://",
            )
        ):
            return value

        return None

    if not isinstance(
        urls,
        list,
    ):
        return None

    fallback: str | None = None

    for item in urls:
        format_name = ""
        value: str | None = None

        if isinstance(
            item,
            str,
        ):
            value = item.strip()

        elif isinstance(
            item,
            dict,
        ):
            raw_value = item.get("value")

            if isinstance(
                raw_value,
                str,
            ):
                value = raw_value.strip()

            raw_format = item.get("format")

            if isinstance(
                raw_format,
                str,
            ):
                format_name = raw_format.strip().lower()

        if not value or not value.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        if format_name == "html":
            return value

        if fallback is None:
            fallback = value

    return fallback


def _extract_meta_v2_fields(
    record: dict[str, object],
) -> dict[str, object]:
    return {
        "title": _meta_text(
            record,
            "title",
        ),
        "authors": _meta_authors(record),
        "journal": _meta_text(
            record,
            "journalTitle",
            "publicationName",
        ),
        "publication_date": (
            _meta_text(
                record,
                "publicationDate",
                "onlineDate",
            )
        ),
        "volume": _meta_scalar_text(
            record,
            "volume",
        ),
        "issue": _meta_scalar_text(
            record,
            "issue",
            "number",
        ),
        "pages": _meta_pages(record),
        "publisher": _meta_text(
            record,
            "publisherName",
            "publisher",
        ),
        "abstract": _meta_text(
            record,
            "abstract",
        ),
        "keywords": _meta_keywords(record),
        "open_access": _meta_scalar_text(
            record,
            "openaccess",
            "openAccess",
        ),
        "copyright": _meta_text(
            record,
            "copyright",
            "rights",
        ),
        "url": _meta_url(record),
    }


def _nonempty_text(
    value: object,
) -> str | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    if not text:
        return None

    return text


def _first_available_text(
    *values: object,
) -> str | None:
    for value in values:
        text = _nonempty_text(value)

        if text:
            return text

    return None


def _longest_available_text(
    *values: object,
) -> str | None:
    candidates: list[str] = []

    for value in values:
        text = _nonempty_text(value)

        if text:
            candidates.append(text)

    if not candidates:
        return None

    return max(
        candidates,
        key=len,
    )


def _merge_sequence_values(
    *values: object,
) -> tuple[str, ...]:
    merged: list[str] = []

    for value in values:
        if not isinstance(
            value,
            (
                tuple,
                list,
            ),
        ):
            continue

        for item in value:
            text = str(item).strip()

            if text and text not in merged:
                merged.append(text)

    return tuple(merged)


def _merge_partial_fields(
    jats_fields: dict[str, object],
    metadata_fields: dict[str, object],
) -> dict[str, object]:
    """
    Merge partial JATS and Springer Meta v2 data.

    JATS is preferred for native article fields.
    Meta v2 fills missing fields.

    Abstract and rights use the longer available value.
    Authors and keywords are conservatively merged.
    """

    return {
        "title": _first_available_text(
            jats_fields.get("title"),
            metadata_fields.get("title"),
        ),
        "authors": _merge_sequence_values(
            jats_fields.get("authors"),
            metadata_fields.get("authors"),
        ),
        "journal": _first_available_text(
            jats_fields.get("journal"),
            metadata_fields.get("journal"),
        ),
        "publication_date": (
            _first_available_text(
                jats_fields.get("publication_date"),
                metadata_fields.get("publication_date"),
            )
        ),
        "volume": _first_available_text(
            jats_fields.get("volume"),
            metadata_fields.get("volume"),
        ),
        "issue": _first_available_text(
            jats_fields.get("issue"),
            metadata_fields.get("issue"),
        ),
        "pages": _first_available_text(
            jats_fields.get("pages"),
            metadata_fields.get("pages"),
        ),
        "publisher": _first_available_text(
            jats_fields.get("publisher"),
            metadata_fields.get("publisher"),
        ),
        "abstract": _longest_available_text(
            jats_fields.get("abstract"),
            metadata_fields.get("abstract"),
        ),
        "keywords": _merge_sequence_values(
            jats_fields.get("keywords"),
            metadata_fields.get("keywords"),
        ),
        "open_access": _first_available_text(
            metadata_fields.get("open_access"),
            jats_fields.get("open_access"),
        ),
        "copyright": (
            _longest_available_text(
                jats_fields.get("copyright"),
                metadata_fields.get("copyright"),
            )
        ),
        "url": _first_available_text(
            metadata_fields.get("url"),
            jats_fields.get("url"),
        ),
    }


def _available_field_names(
    fields: dict[str, object],
) -> list[str]:
    available: list[str] = []

    for key, value in fields.items():
        if (
            isinstance(
                value,
                str,
            )
            and value.strip()
        ) or (
            isinstance(
                value,
                (
                    tuple,
                    list,
                ),
            )
            and value
        ):
            available.append(key)

    return available


def _render_partial_markdown(
    doi: str,
    *,
    fields: dict[str, object],
    paper_directory: Path,
    library_root: Path,
) -> str:
    normalized = normalize_doi(doi)

    title = _nonempty_text(fields.get("title"))

    authors = fields.get("authors")

    journal = _nonempty_text(fields.get("journal"))

    publication_date = _nonempty_text(fields.get("publication_date"))

    volume = _nonempty_text(fields.get("volume"))

    issue = _nonempty_text(fields.get("issue"))

    pages = _nonempty_text(fields.get("pages"))

    publisher = _nonempty_text(fields.get("publisher"))

    abstract = _nonempty_text(fields.get("abstract"))

    keywords = fields.get("keywords")

    open_access = _nonempty_text(fields.get("open_access"))

    copyright_text = _nonempty_text(fields.get("copyright"))

    url = _nonempty_text(fields.get("url"))

    lines: list[str] = []

    if title:
        lines.append(f"# {title}")
    else:
        lines.append(f"# {normalized}")

    lines.append("")
    lines.append(f"DOI: {normalized}")

    if (
        isinstance(
            authors,
            tuple,
        )
        and authors
    ):
        lines.append("Authors: " + "; ".join(authors))

    if journal:
        lines.append(f"Journal: {journal}")

    if publication_date:
        lines.append(f"Published: {publication_date}")

    if volume:
        lines.append(f"Volume: {volume}")

    if issue:
        lines.append(f"Issue: {issue}")

    if pages:
        lines.append(f"Pages: {pages}")

    if publisher:
        lines.append(f"Publisher: {publisher}")

    if open_access:
        lines.append(f"Open access metadata: {open_access}")

    if (
        isinstance(
            keywords,
            tuple,
        )
        and keywords
    ):
        lines.append("Keywords: " + "; ".join(keywords))

    if abstract:
        lines.append("")
        lines.append("## Abstract")
        lines.append("")
        lines.append(abstract)

    if copyright_text:
        lines.append("")
        lines.append("## Rights information")
        lines.append("")
        lines.append(copyright_text)

    if url:
        lines.append("")
        lines.append("## Publisher link")
        lines.append("")
        lines.append(url)

    lines.append("")
    lines.append("## Access status")
    lines.append("")
    lines.append(
        "> The complete publisher full text/PDF "
        "is not currently available through the "
        "configured Springer Nature access."
    )
    lines.append(
        "> This Markdown contains all useful "
        "bibliographic/abstract information that "
        "PaperFlow could recover from available "
        "Springer Nature structured sources. "
        "Missing article sections were not "
        "inferred or invented."
    )
    lines.append("")
    lines.append("> If you legally obtain the main article PDF, place exactly ONE `.pdf` file in:")
    lines.append(f"> `{paper_directory}`")
    lines.append("> The PDF filename can be anything.")
    lines.append("")
    lines.append("> Then rerun:")
    lines.append(f'> `paperflow process {normalized} --library-root "{library_root}"`')

    return "\n".join(lines).rstrip() + "\n"


def write_restricted_access_artifacts(
    doi: str,
    *,
    route: str,
    paper_directory: str | Path,
    raw_markdown_path: str | Path,
    llm_markdown_path: str | Path,
    qa_path: str | Path,
    library_root: str | Path,
    api_key: str,
    timeout: float,
    reason: str,
    existing_xml_path: str | Path | None = None,
) -> RestrictedAccessArtifacts:
    """
    Create a recoverable restricted-access result.

    Recovery sources:

        partial JATS/XML, if available
        +
        Springer Meta v2 JSON

    The dedicated SPRINGER_META_API_KEY environment variable is
    preferred for the Meta v2 request.

    The api_key argument remains as a backward-compatible fallback so
    existing pipeline callers do not need to change immediately.

    This function remains the final fallback after normal JATS/PDF
    acquisition routes have already failed.
    """

    normalized = normalize_doi(doi)

    paper_directory = Path(paper_directory)

    raw_markdown_path = Path(raw_markdown_path)

    llm_markdown_path = Path(llm_markdown_path)

    qa_path = Path(qa_path)

    library_root = Path(library_root)

    paper_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    #
    # 1. Preserve and inspect partial JATS/XML if available.
    #
    partial_xml_path: Path | None = None
    partial_xml_content: bytes | None = None
    partial_fields: dict[str, object] = {}

    if existing_xml_path is not None:
        candidate = Path(existing_xml_path)

        if candidate.is_file():
            try:
                candidate_content = candidate.read_bytes()

                if _xml_contains_doi(
                    candidate_content,
                    normalized,
                ):
                    partial_xml_path = candidate

                    partial_xml_content = candidate_content

                    partial_fields = _extract_partial_fields(candidate_content)

            except (
                OSError,
                SpringerMetadataRecoveryError,
            ):
                partial_xml_path = None
                partial_xml_content = None
                partial_fields = {}

    #
    # 2. Resolve the dedicated Meta API key.
    #
    metadata_json_path: Path | None = None
    metadata_payload: dict[str, object] | None = None
    metadata_fields: dict[str, object] = {}
    metadata_error: str | None = None

    try:

        (
            metadata_payload,
            metadata_record,
        ) = _fetch_meta_v2_record(
            normalized,
            api_key=api_key,
            timeout=timeout,
        )

        #
        # Do not persist the complete raw API response.
        #
        # Some responses may contain request-management fields that
        # include API credentials. Save only the matched record and
        # the non-secret query value.
        #
        safe_metadata_artifact = {
            "query": (metadata_payload.get("query")),
            "record": (metadata_record),
        }

        metadata_json_path = paper_directory / "springer_meta.json"

        metadata_json_path.write_text(
            json.dumps(
                safe_metadata_artifact,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        metadata_fields = _extract_meta_v2_fields(metadata_record)

    except (
        OSError,
        SpringerMetadataRecoveryError,
    ) as exc:
        metadata_error = f"{type(exc).__name__}: {exc}"

    #
    # 3. Merge all available structured information.
    #
    merged_fields = _merge_partial_fields(
        partial_fields,
        metadata_fields,
    )

    #
    # 4. Render partial Markdown.
    #
    markdown = _render_partial_markdown(
        normalized,
        fields=merged_fields,
        paper_directory=(paper_directory),
        library_root=(library_root),
    )

    raw_markdown_path.write_text(
        markdown,
        encoding="utf-8",
    )

    llm_markdown_path.write_text(
        markdown,
        encoding="utf-8",
    )

    rerun_command = f'paperflow process {normalized} --library-root "{library_root}"'

    sources_used: list[str] = []

    if partial_xml_content is not None:
        sources_used.append("partial_jats_xml")

    if metadata_payload is not None:
        sources_used.append("springer_meta_v2")

    available_fields = _available_field_names(merged_fields)

    #
    # 5. Recovery log.
    #
    access_json_path = paper_directory / "access.json"

    access_payload = {
        "doi": normalized,
        "route": route,
        "status": ("restricted_access"),
        "full_text_available": False,
        "reason": reason,
        "sources_used": sources_used,
        "available_fields": (available_fields),
        "partial_xml": (str(partial_xml_path) if partial_xml_path is not None else None),
        "metadata_json": (str(metadata_json_path) if metadata_json_path is not None else None),
        "metadata_error": (metadata_error),
        "pdf_directory": str(paper_directory),
        "pdf_filename_rule": (
            "Place exactly one PDF file in this directory. The filename may be arbitrary."
        ),
        "rerun_command": (rerun_command),
    }

    access_json_path.write_text(
        json.dumps(
            access_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    #
    # 6. QA.
    #
    warnings = [
        (
            "Complete publisher full text/PDF "
            "is not currently available through "
            "the configured access."
        ),
        ("Partial structured metadata Markdown was generated."),
        (
            "Place exactly one legally obtained "
            "PDF in the paper directory and rerun "
            "the same process command to use MinerU."
        ),
    ]

    if metadata_error is not None:
        warnings.append(
            "Springer Meta v2 retrieval "
            "was unavailable; existing partial "
            "XML information was used instead."
        )

    qa_payload = {
        "doi": normalized,
        "route": route,
        "source": ("springer_restricted_partial"),
        "status": "warning",
        "partial_content": True,
        "access_restricted": True,
        "full_text_available": False,
        "reason": reason,
        "sources_used": sources_used,
        "available_fields": (available_fields),
        "partial_xml": (str(partial_xml_path) if partial_xml_path is not None else None),
        "metadata_json": (str(metadata_json_path) if metadata_json_path is not None else None),
        "metadata_error": (metadata_error),
        "access_json": str(access_json_path),
        "pdf_directory": str(paper_directory),
        "rerun_command": (rerun_command),
        "warnings": warnings,
        "failures": [],
    }

    qa_path.write_text(
        json.dumps(
            qa_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return RestrictedAccessArtifacts(
        markdown_path=(llm_markdown_path),
        raw_markdown_path=(raw_markdown_path),
        qa_path=qa_path,
        access_json_path=(access_json_path),
        partial_xml_path=(partial_xml_path),
        metadata_json_path=(metadata_json_path),
        metadata_error=(metadata_error),
    )
