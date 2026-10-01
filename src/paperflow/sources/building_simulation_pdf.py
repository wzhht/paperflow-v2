from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx
from lxml import html
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from paperflow.utils.doi import normalize_doi

SPRINGER_ARTICLE_BASE = "https://link.springer.com/article"
SPRINGER_PDF_BASE = "https://link.springer.com/content/pdf"


class BuildingSimulationPdfError(RuntimeError):
    """Base Building Simulation PDF acquisition error."""


class BuildingSimulationPdfNetworkError(
    BuildingSimulationPdfError
):
    """Network communication with Springer failed."""


class BuildingSimulationPdfHTTPError(
    BuildingSimulationPdfError
):
    """Springer returned an HTTP error."""


class BuildingSimulationPdfContentError(
    BuildingSimulationPdfError
):
    """Springer did not return a usable main article PDF."""


@dataclass(frozen=True)
class BuildingSimulationPdfPayload:
    doi: str
    url: str
    content: bytes
    content_type: str


def _validated_doi(
    doi: str,
) -> str:
    normalized = normalize_doi(
        doi
    )

    if not normalized.startswith(
        "10.1007/s12273"
    ):
        raise ValueError(
            "Building Simulation PDF acquisition "
            "requires a 10.1007/s12273... DOI."
        )

    return normalized


def build_building_simulation_article_url(
    doi: str,
) -> str:
    normalized = _validated_doi(
        doi
    )

    encoded = quote(
        normalized,
        safe="/-._~",
    )

    return (
        f"{SPRINGER_ARTICLE_BASE}/"
        f"{encoded}"
    )


def build_building_simulation_pdf_url(
    doi: str,
) -> str:
    normalized = _validated_doi(
        doi
    )

    encoded = quote(
        normalized,
        safe="/-._~",
    )

    return (
        f"{SPRINGER_PDF_BASE}/"
        f"{encoded}.pdf"
    )


def _collapse_text(
    value: str,
) -> str:
    return " ".join(
        value.split()
    )


def _find_main_pdf_href(
    html_content: str,
    doi: str,
) -> str | None:
    """
    Locate the main article PDF.

    Explicitly avoid supplementary-material PDFs.
    """

    normalized = _validated_doi(
        doi
    ).lower()

    expected_path = (
        f"/content/pdf/"
        f"{normalized}.pdf"
    )

    try:
        document = html.fromstring(
            html_content
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise BuildingSimulationPdfContentError(
            "Springer article page could not "
            "be parsed as HTML."
        ) from exc

    candidates: list[
        tuple[int, str]
    ] = []

    for anchor in document.xpath(
        "//a[@href]"
    ):
        href = str(
            anchor.get("href")
            or ""
        ).strip()

        if not href:
            continue

        parsed = urlparse(
            href
        )

        path = unquote(
            parsed.path
            or ""
        ).lower()

        if not path.endswith(
            ".pdf"
        ):
            continue

        text = _collapse_text(
            "".join(
                anchor.itertext()
            )
        ).lower()

        combined = (
            f"{text} {path}"
        )

        if any(
            marker in combined
            for marker in (
                "supplement",
                "electronic supplementary",
                "esm",
                "moesm",
                "peer review",
            )
        ):
            continue

        score = 0

        if path == expected_path:
            score += 100

        if text == "download pdf":
            score += 50

        if text == "article pdf":
            score += 40

        if (
            "/content/pdf/"
            in path
            and normalized in path
        ):
            score += 25

        if score:
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


class BuildingSimulationPdfClient:
    def __init__(
        self,
        timeout: float = 60.0,
        transport: (
            httpx.BaseTransport
            | None
        ) = None,
    ):
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "User-Agent": (
                    "PaperFlow/0.2.0 "
                    "(academic paper processing)"
                ),
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
        retry=retry_if_exception_type(
            httpx.RequestError
        ),
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
            raise BuildingSimulationPdfNetworkError(
                "Springer request failed "
                f"after retries for DOI "
                f"{doi} during {stage}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            ) from exc

        if response.is_error:
            content_type = (
                response.headers.get(
                    "content-type",
                    "",
                )
            )

            raise BuildingSimulationPdfHTTPError(
                "Springer returned "
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
    ) -> BuildingSimulationPdfPayload:
        normalized = _validated_doi(
            doi
        )

        article_url = (
            build_building_simulation_article_url(
                normalized
            )
        )

        page_response = self._request(
            article_url,
            accept=(
                "text/html,"
                "application/xhtml+xml"
            ),
            doi=normalized,
            stage="article_page",
        )

        href = _find_main_pdf_href(
            page_response.text,
            normalized,
        )

        if href is None:
            #
            # Springer uses a stable direct main-article
            # PDF URL for Building Simulation.
            #
            pdf_url = (
                build_building_simulation_pdf_url(
                    normalized
                )
            )
        else:
            pdf_url = urljoin(
                str(page_response.url),
                href,
            )

        pdf_response = self._request(
            pdf_url,
            accept="application/pdf",
            doi=normalized,
            stage="article_pdf",
        )

        content = (
            pdf_response.content
        )

        content_type = (
            pdf_response.headers.get(
                "content-type",
                "",
            )
        )

        if not content.startswith(
            b"%PDF-"
        ):
            preview = ""

            try:
                preview = (
                    pdf_response.text[
                        :500
                    ].strip()
                )
            except UnicodeError:
                pass

            raise BuildingSimulationPdfContentError(
                "Resolved Building Simulation "
                "article PDF URL did not return "
                f"a PDF for DOI {normalized}. "
                f"URL: {pdf_response.url}. "
                f"Content-Type: {content_type}. "
                f"Response preview: {preview}"
            )

        return BuildingSimulationPdfPayload(
            doi=normalized,
            url=str(
                pdf_response.url
            ),
            content=content,
            content_type=content_type,
        )