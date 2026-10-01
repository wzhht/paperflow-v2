from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse

import httpx
from lxml import html
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from paperflow.utils.doi import normalize_doi

NATURE_ARTICLE_BASE = "https://www.nature.com/articles"


class NaturePdfError(RuntimeError):
    """Base Nature PDF acquisition error."""


class NaturePdfNetworkError(NaturePdfError):
    """Network communication with Nature failed."""


class NaturePdfHTTPError(NaturePdfError):
    """Nature returned an HTTP error."""


class NaturePdfContentError(NaturePdfError):
    """Nature did not return a usable article PDF."""


@dataclass(frozen=True)
class NaturePdfPayload:
    doi: str
    url: str
    content: bytes
    content_type: str


def _nature_suffix(
    doi: str,
) -> str:
    normalized = normalize_doi(doi)

    if not normalized.startswith("10.1038/"):
        raise ValueError("Nature PDF acquisition requires a 10.1038 DOI.")

    return normalized.split(
        "/",
        1,
    )[1]


def build_nature_article_url(
    doi: str,
) -> str:
    suffix = _nature_suffix(doi)

    encoded = quote(
        suffix,
        safe="-._~",
    )

    return f"{NATURE_ARTICLE_BASE}/{encoded}"


def build_nature_pdf_url(
    doi: str,
) -> str:
    """
    Legacy direct PDF guess.

    Kept as a conservative fallback only.

    Final Nature articles commonly use:

        /articles/<suffix>.pdf

    Very new Article in Press papers may instead use:

        /articles/<suffix>_reference.pdf

    fetch_pdf() therefore resolves the actual PDF link from
    the article page before using this fallback.
    """

    return build_nature_article_url(doi) + ".pdf"


def _collapse_text(
    value: str,
) -> str:
    return " ".join(value.split())


def _is_supplementary_pdf(
    *,
    text: str,
    path: str,
) -> bool:
    combined = (f"{text} {path}").lower()

    markers = (
        "supplementary",
        "peer review",
        "transparent peer",
        "source data",
        "moesm",
        "_esm.pdf",
    )

    return any(marker in combined for marker in markers)


def _find_main_pdf_href(
    html_content: str,
    doi: str,
) -> str | None:
    """
    Locate the main article PDF link on a Nature article page.

    Important distinction:

    - final Version of Record:
        <suffix>.pdf

    - very new Article in Press:
        <suffix>_reference.pdf

    Supplementary information and peer-review PDFs are rejected.
    """

    suffix = _nature_suffix(doi).lower()

    try:
        document = html.fromstring(html_content)

    except (
        ValueError,
        TypeError,
    ) as exc:
        raise NaturePdfContentError("Nature article page could not be parsed as HTML.") from exc

    candidates: list[tuple[int, str]] = []

    for anchor in document.xpath("//a[@href]"):
        href = str(anchor.get("href") or "").strip()

        if not href:
            continue

        parsed = urlparse(href)

        path = (parsed.path or "").lower()

        if not path.endswith(".pdf"):
            continue

        text = _collapse_text("".join(anchor.itertext()))

        if _is_supplementary_pdf(
            text=text,
            path=path,
        ):
            continue

        #
        # Main article PDF should contain the article's
        # DOI suffix in its path.
        #
        if suffix not in path:
            continue

        score = 0

        normalized_text = text.lower()

        if normalized_text == "download pdf":
            score += 100

        if path.endswith(f"/{suffix}_reference.pdf"):
            score += 50

        if path.endswith(f"/{suffix}.pdf"):
            score += 40

        if score == 0:
            score = 1

        candidates.append(
            (
                score,
                href,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


class NaturePdfClient:
    def __init__(
        self,
        timeout: float = 60.0,
        transport: (httpx.BaseTransport | None) = None,
    ):
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "User-Agent": ("PaperFlow/0.2.0 (academic paper processing)"),
            },
        )

    def close(
        self,
    ) -> None:
        self.client.close()

    def __enter__(
        self,
    ):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type(httpx.RequestError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(
            multiplier=1,
            min=1,
            max=5,
        ),
        reraise=True,
    )
    def _get(
        self,
        url: str,
        *,
        accept: str,
    ) -> httpx.Response:
        return self.client.get(
            url,
            headers={
                "Accept": accept,
            },
        )

    def _request(
        self,
        url: str,
        *,
        accept: str,
        doi: str,
        stage: str,
    ) -> httpx.Response:
        try:
            response = self._get(
                url,
                accept=accept,
            )

        except httpx.RequestError as exc:
            raise NaturePdfNetworkError(
                "Nature request failed "
                f"after retries for DOI "
                f"{doi} during {stage}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            ) from exc

        if response.is_error:
            content_type = response.headers.get(
                "content-type",
                "",
            )

            raise NaturePdfHTTPError(
                "Nature returned "
                f"HTTP {response.status_code} "
                f"for DOI {doi} "
                f"during {stage}. "
                f"Content-Type: "
                f"{content_type}."
            )

        return response

    def fetch_pdf(
        self,
        doi: str,
    ) -> NaturePdfPayload:
        """
        Fetch the main Nature article PDF.

        Resolution strategy:

        1. Fetch Nature article HTML.
        2. Locate the main "Download PDF" link.
        3. Reject supplementary / peer-review PDFs.
        4. Resolve relative URL.
        5. Download and validate PDF signature.
        6. If no main PDF link exists in HTML, try the legacy
           <article>.pdf URL as a conservative fallback.
        """

        normalized = normalize_doi(doi)

        article_url = build_nature_article_url(normalized)

        page_response = self._request(
            article_url,
            accept=("text/html,application/xhtml+xml"),
            doi=normalized,
            stage="article_page",
        )

        href = _find_main_pdf_href(
            page_response.text,
            normalized,
        )

        if href is not None:
            pdf_url = urljoin(
                str(page_response.url),
                href,
            )

        else:
            #
            # Conservative backward-compatible fallback.
            #
            pdf_url = build_nature_pdf_url(normalized)

        pdf_response = self._request(
            pdf_url,
            accept=("application/pdf"),
            doi=normalized,
            stage="article_pdf",
        )

        content = pdf_response.content

        content_type = pdf_response.headers.get(
            "content-type",
            "",
        )

        if not content.startswith(b"%PDF-"):
            raise NaturePdfContentError(
                "Resolved Nature article "
                "PDF URL did not return "
                "a PDF for DOI "
                f"{normalized}. "
                f"URL: "
                f"{pdf_response.url}. "
                f"HTTP status: "
                f"{pdf_response.status_code}. "
                f"Content-Type: "
                f"{content_type or 'unknown'}."
            )

        return NaturePdfPayload(
            doi=normalized,
            url=str(pdf_response.url),
            content=content,
            content_type=(content_type),
        )
