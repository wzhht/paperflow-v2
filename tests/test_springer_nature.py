import httpx
import pytest
from lxml import etree

from paperflow.sources.springer_nature import (
    SpringerNatureClient,
    SpringerNatureContentError,
    SpringerNatureHTTPError,
)

DOI = "10.1038/s41467-019-11026-x"


def _response_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<response>
  <records>
    <article>
      <front>
        <article-meta>
          <article-id pub-id-type="doi">
            10.1038/s41467-019-11026-x
          </article-id>
          <title-group>
            <article-title>
              Example Nature article
            </article-title>
          </title-group>
        </article-meta>
      </front>
      <body>
        <sec>
          <title>Introduction</title>
          <p>Example full-text paragraph.</p>
        </sec>
      </body>
    </article>
  </records>
</response>
"""


def test_fetch_jats_extracts_matching_article():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.params["q"] == f"doi:{DOI}"

        assert request.url.params["api_key"] == "test-key"

        return httpx.Response(
            200,
            content=_response_xml(),
            headers={
                "Content-Type": "application/xml",
            },
        )

    transport = httpx.MockTransport(handler)

    with SpringerNatureClient(
        api_key="test-key",
        transport=transport,
    ) as client:
        payload = client.fetch_jats(DOI)

    assert payload.doi == DOI
    assert payload.article_count == 1
    assert payload.response_xml == _response_xml()

    article = etree.fromstring(payload.article_xml)

    assert etree.QName(article).localname == "article"

    doi_values = article.xpath(".//*[local-name()='article-id' and @pub-id-type='doi']/text()")

    assert DOI in {str(value).strip() for value in doi_values}


def test_fetch_jats_rejects_wrong_article():
    response_xml = b"""<?xml version="1.0"?>
<response>
  <records>
    <article>
      <front>
        <article-meta>
          <article-id pub-id-type="doi">
            10.1038/example-wrong-doi
          </article-id>
        </article-meta>
      </front>
    </article>
  </records>
</response>
"""

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            content=response_xml,
        )

    transport = httpx.MockTransport(handler)

    with SpringerNatureClient(
        api_key="test-key",
        transport=transport,
    ) as client, pytest.raises(SpringerNatureContentError):
        client.fetch_jats(DOI)


def test_fetch_jats_rejects_invalid_xml():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not xml",
        )

    transport = httpx.MockTransport(handler)

    with SpringerNatureClient(
        api_key="test-key",
        transport=transport,
    ) as client, pytest.raises(SpringerNatureContentError):
        client.fetch_jats(DOI)


def test_fetch_jats_reports_http_error():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            403,
            content=b"Forbidden",
        )

    transport = httpx.MockTransport(handler)

    with SpringerNatureClient(
        api_key="test-key",
        transport=transport,
    ) as client, pytest.raises(SpringerNatureHTTPError):
        client.fetch_jats(DOI)
