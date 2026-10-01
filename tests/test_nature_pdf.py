import httpx
import pytest

from paperflow.sources.nature_pdf import (
    NaturePdfClient,
    NaturePdfContentError,
    NaturePdfHTTPError,
    build_nature_article_url,
    build_nature_pdf_url,
)

DOI = "10.1038/s41467-026-78118-3"


def test_build_nature_article_url():
    assert build_nature_article_url(DOI) == ("https://www.nature.com/articles/s41467-026-78118-3")


def test_build_nature_pdf_url():
    assert build_nature_pdf_url(DOI) == ("https://www.nature.com/articles/s41467-026-78118-3.pdf")


def test_build_nature_url_rejects_other_doi():
    with pytest.raises(ValueError):
        build_nature_article_url("10.1016/example")


def test_fetch_nature_reference_pdf():
    article_html = """
    <html>
      <body>
        <a href="/articles/s41467-026-78118-3_reference.pdf">
          Download PDF
        </a>

        <a href="https://media.springernature.com/original/example_ESM.pdf">
          Supplementary Information (download PDF)
        </a>

        <a href="https://media.springernature.com/original/review_ESM.pdf">
          Transparent Peer Review file (download PDF)
        </a>
      </body>
    </html>
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url)

        if url == ("https://www.nature.com/articles/s41467-026-78118-3"):
            return httpx.Response(
                200,
                headers={"Content-Type": ("text/html; charset=utf-8")},
                text=article_html,
                request=request,
            )

        if url == ("https://www.nature.com/articles/s41467-026-78118-3_reference.pdf"):
            return httpx.Response(
                200,
                headers={"Content-Type": ("application/pdf")},
                content=(b"%PDF-1.7\narticle"),
                request=request,
            )

        raise AssertionError(f"Unexpected URL: {url}")

    transport = httpx.MockTransport(handler)

    with NaturePdfClient(transport=transport) as client:
        result = client.fetch_pdf(DOI)

    assert result.url == ("https://www.nature.com/articles/s41467-026-78118-3_reference.pdf")

    assert result.content.startswith(b"%PDF-")


def test_fetch_nature_standard_pdf():
    article_html = """
    <html>
      <body>
        <a href="/articles/s41467-026-78118-3.pdf">
          Download PDF
        </a>
      </body>
    </html>
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url)

        if url.endswith("s41467-026-78118-3"):
            return httpx.Response(
                200,
                headers={"Content-Type": ("text/html")},
                text=article_html,
                request=request,
            )

        if url.endswith("s41467-026-78118-3.pdf"):
            return httpx.Response(
                200,
                headers={"Content-Type": ("application/pdf")},
                content=(b"%PDF-1.7\narticle"),
                request=request,
            )

        raise AssertionError(f"Unexpected URL: {url}")

    transport = httpx.MockTransport(handler)

    with NaturePdfClient(transport=transport) as client:
        result = client.fetch_pdf(DOI)

    assert result.url.endswith("s41467-026-78118-3.pdf")


def test_fetch_nature_pdf_uses_legacy_fallback():
    article_html = """
    <html>
      <body>
        <p>No PDF anchor here.</p>
      </body>
    </html>
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url)

        if url.endswith("s41467-026-78118-3"):
            return httpx.Response(
                200,
                headers={"Content-Type": ("text/html")},
                text=article_html,
                request=request,
            )

        if url.endswith("s41467-026-78118-3.pdf"):
            return httpx.Response(
                200,
                headers={"Content-Type": ("application/pdf")},
                content=(b"%PDF-1.7\nlegacy"),
                request=request,
            )

        raise AssertionError(f"Unexpected URL: {url}")

    transport = httpx.MockTransport(handler)

    with NaturePdfClient(transport=transport) as client:
        result = client.fetch_pdf(DOI)

    assert result.content.startswith(b"%PDF-")


def test_fetch_nature_pdf_rejects_html_pdf_response():
    article_html = """
    <html>
      <body>
        <a href="/articles/s41467-026-78118-3_reference.pdf">
          Download PDF
        </a>
      </body>
    </html>
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(request.url)

        if url.endswith("s41467-026-78118-3"):
            return httpx.Response(
                200,
                headers={"Content-Type": ("text/html")},
                text=article_html,
                request=request,
            )

        return httpx.Response(
            200,
            headers={"Content-Type": ("text/html")},
            text=("<html>not a pdf</html>"),
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with (
        NaturePdfClient(transport=transport) as client,
        pytest.raises(NaturePdfContentError),
    ):
        client.fetch_pdf(DOI)


def test_fetch_nature_article_page_reports_http_error():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"Content-Type": ("text/html")},
            content=b"Forbidden",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with (
        NaturePdfClient(transport=transport) as client,
        pytest.raises(NaturePdfHTTPError),
    ):
        client.fetch_pdf(DOI)
