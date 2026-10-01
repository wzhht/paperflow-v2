from __future__ import annotations

from dataclasses import dataclass

import httpx
from lxml import etree
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from paperflow.utils.doi import normalize_doi

SPRINGER_NATURE_OPEN_ACCESS_JATS_API = "https://api.springernature.com/openaccess/jats"


class SpringerNatureError(RuntimeError):
    """Base Springer Nature source error."""


class SpringerNatureNetworkError(SpringerNatureError):
    """Network communication with Springer Nature failed."""


class SpringerNatureHTTPError(SpringerNatureError):
    """Springer Nature returned an HTTP error."""


class SpringerNatureContentError(SpringerNatureError):
    """Springer Nature returned unusable JATS content."""


@dataclass(frozen=True)
class SpringerNatureJatsPayload:
    doi: str
    response_xml: bytes
    article_xml: bytes
    article_count: int


class SpringerNatureClient:
    def __init__(
        self,
        api_key: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise ValueError("Springer Nature API key cannot be empty.")

        self.api_key = api_key

        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "Accept": "application/xml,text/xml",
                "User-Agent": "PaperFlow/0.2.0",
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
        doi: str,
    ) -> httpx.Response:
        return self.client.get(
            SPRINGER_NATURE_OPEN_ACCESS_JATS_API,
            params={
                "q": f"doi:{doi}",
                "api_key": self.api_key,
                "p": "10",
            },
        )

    def fetch_jats(
        self,
        doi: str,
    ) -> SpringerNatureJatsPayload:
        doi = normalize_doi(doi)

        try:
            response = self._get(doi)

        except httpx.RequestError as exc:
            raise SpringerNatureNetworkError(
                "Springer Nature network request "
                f"failed after retries for DOI {doi}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if response.is_error:
            raise SpringerNatureHTTPError(
                f"Springer Nature returned HTTP {response.status_code} for DOI {doi}."
            )

        return _extract_jats_payload(
            doi=doi,
            response_xml=response.content,
        )


def _extract_jats_payload(
    doi: str,
    response_xml: bytes,
) -> SpringerNatureJatsPayload:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
    )

    try:
        root = etree.fromstring(
            response_xml,
            parser=parser,
        )

    except etree.XMLSyntaxError as exc:
        raise SpringerNatureContentError("Springer Nature response is not valid XML.") from exc

    articles: list[etree._Element]

    if etree.QName(root).localname == "article":
        articles = [root]
    else:
        articles = list(root.xpath(".//*[local-name()='article']"))

    article = _find_matching_article(
        articles,
        doi,
    )

    if article is None:
        raise SpringerNatureContentError(
            f"No JATS article matching DOI {doi} was found in the response."
        )

    article_xml = etree.tostring(
        article,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )

    return SpringerNatureJatsPayload(
        doi=doi,
        response_xml=response_xml,
        article_xml=article_xml,
        article_count=len(articles),
    )


def _find_matching_article(
    articles: list[etree._Element],
    doi: str,
) -> etree._Element | None:
    target = doi.lower()

    for article in articles:
        values = article.xpath(".//*[local-name()='article-id' and @pub-id-type='doi']/text()")

        for value in values:
            candidate = str(value).strip().lower()

            if candidate == target:
                return article

    return None
