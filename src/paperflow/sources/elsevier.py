from urllib.parse import quote

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from paperflow.utils.doi import normalize_doi

ELSEVIER_ARTICLE_API = "https://api.elsevier.com/content/article/doi"


class ElsevierError(RuntimeError):
    """Base Elsevier source error."""


class ElsevierNetworkError(ElsevierError):
    """Network communication with Elsevier failed."""


class ElsevierHTTPError(ElsevierError):
    """Elsevier returned an HTTP error."""


class ElsevierContentError(ElsevierError):
    """Elsevier returned unexpected content."""


class ElsevierClient:
    def __init__(
        self,
        api_key: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise ValueError("Elsevier API key cannot be empty.")

        self.api_key = api_key

        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "X-ELS-APIKey": api_key,
                "User-Agent": "PaperFlow/0.1.0",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()

    @staticmethod
    def _article_url(
        doi: str,
    ) -> str:
        doi = normalize_doi(doi)

        encoded = quote(
            doi,
            safe="/",
        )

        return f"{ELSEVIER_ARTICLE_API}/{encoded}"

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
        accept: str,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        """
        Execute one HTTP GET request.

        Network-level httpx.RequestError exceptions
        are retried automatically by tenacity.

        HTTP responses such as 400, 401, 403, 404,
        429, or 500 are returned normally to
        _request() and are not retried here.
        """

        return self.client.get(
            url,
            headers={
                "Accept": accept,
            },
            params=params,
        )

    def _request(
        self,
        doi: str,
        accept: str,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        normalized_doi = normalize_doi(doi)

        try:
            response = self._get(
                url=self._article_url(normalized_doi),
                accept=accept,
                params=params,
            )

        except httpx.RequestError as exc:
            raise ElsevierNetworkError(
                f"Elsevier network request failed "
                f"after retries for DOI "
                f"{normalized_doi}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if response.is_error:
            content_type = response.headers.get(
                "content-type",
                "",
            )

            body_preview = response.text[:1000].strip()

            raise ElsevierHTTPError(
                f"Elsevier API returned "
                f"HTTP {response.status_code} "
                f"for DOI {normalized_doi}. "
                f"Content-Type: {content_type}. "
                f"Response: {body_preview}"
            )

        return response

    def fetch_metadata(
        self,
        doi: str,
    ) -> dict:
        response = self._request(
            doi,
            accept="application/json",
        )

        try:
            return response.json()

        except ValueError as exc:
            raise ElsevierContentError("Elsevier metadata response was not valid JSON.") from exc

    def fetch_xml(
        self,
        doi: str,
    ) -> bytes:
        """
        Fetch structured article XML.

        Important:
        Do NOT force view=FULL here.

        Elsevier may return structured full text
        when entitlement allows it, while an
        explicit FULL view is not valid for the
        XML route in our tested workflow.
        """

        response = self._request(
            doi,
            accept="text/xml",
        )

        content = response.content

        if not content.lstrip().startswith(b"<"):
            raise ElsevierContentError("Elsevier XML response does not look like XML.")

        return content

    def fetch_pdf(
        self,
        doi: str,
    ) -> bytes:
        """
        Fetch article PDF using view=FULL.

        Availability depends on the current
        Elsevier entitlement context.
        """

        response = self._request(
            doi,
            accept="application/pdf",
            params={
                "view": "FULL",
            },
        )

        content = response.content

        if not content.startswith(b"%PDF-"):
            raise ElsevierContentError("Elsevier PDF response does not have a valid PDF signature.")

        return content
