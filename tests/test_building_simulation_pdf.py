import httpx
import pytest

from paperflow.sources.building_simulation_pdf import (
    BuildingSimulationPdfClient,
    BuildingSimulationPdfContentError,
    BuildingSimulationPdfHTTPError,
    build_building_simulation_article_url,
    build_building_simulation_pdf_url,
)

DOI = "10.1007/s12273-026-1484-2"


def test_build_article_url():
    assert (
        build_building_simulation_article_url(
            DOI
        )
        == (
            "https://link.springer.com/article/"
            "10.1007/s12273-026-1484-2"
        )
    )


def test_build_pdf_url():
    assert (
        build_building_simulation_pdf_url(
            DOI
        )
        == (
            "https://link.springer.com/content/pdf/"
            "10.1007/s12273-026-1484-2.pdf"
        )
    )


def test_rejects_other_springer_doi():
    with pytest.raises(
        ValueError
    ):
        build_building_simulation_pdf_url(
            "10.1007/s00100-026-1234-5"
        )


def test_fetch_main_pdf_ignores_supplement():
    article_html = """
    <html>
      <body>
        <a href="/content/pdf/10.1007/s12273-026-1484-2.pdf">
          Download PDF
        </a>

        <a href="https://media.springernature.com/example_ESM.pdf">
          Electronic Supplementary Material (download PDF)
        </a>
      </body>
    </html>
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(
            request.url
        )

        if url == (
            "https://link.springer.com/article/"
            "10.1007/s12273-026-1484-2"
        ):
            return httpx.Response(
                200,
                headers={
                    "Content-Type":
                    "text/html; charset=utf-8"
                },
                text=article_html,
                request=request,
            )

        if url == (
            "https://link.springer.com/content/pdf/"
            "10.1007/s12273-026-1484-2.pdf"
        ):
            return httpx.Response(
                200,
                headers={
                    "Content-Type":
                    "application/pdf"
                },
                content=(
                    b"%PDF-1.7\n"
                    b"main article"
                ),
                request=request,
            )

        raise AssertionError(
            f"Unexpected URL: {url}"
        )

    transport = httpx.MockTransport(
        handler
    )

    with BuildingSimulationPdfClient(
        transport=transport
    ) as client:
        result = client.fetch_pdf(
            DOI
        )

    assert result.content.startswith(
        b"%PDF-"
    )

    assert result.url.endswith(
        "10.1007/"
        "s12273-026-1484-2.pdf"
    )


def test_fetch_uses_direct_fallback():
    article_html = """
    <html>
      <body>
        <p>No usable PDF anchor.</p>
      </body>
    </html>
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        url = str(
            request.url
        )

        if "/article/" in url:
            return httpx.Response(
                200,
                headers={
                    "Content-Type":
                    "text/html"
                },
                text=article_html,
                request=request,
            )

        if "/content/pdf/" in url:
            return httpx.Response(
                200,
                headers={
                    "Content-Type":
                    "application/pdf"
                },
                content=b"%PDF-1.7\narticle",
                request=request,
            )

        raise AssertionError(
            f"Unexpected URL: {url}"
        )

    transport = httpx.MockTransport(
        handler
    )

    with BuildingSimulationPdfClient(
        transport=transport
    ) as client:
        result = client.fetch_pdf(
            DOI
        )

    assert result.content.startswith(
        b"%PDF-"
    )


def test_fetch_rejects_html_as_pdf():
    article_html = """
    <html>
      <body>
        <a href="/content/pdf/10.1007/s12273-026-1484-2.pdf">
          Download PDF
        </a>
      </body>
    </html>
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if "/article/" in str(
            request.url
        ):
            return httpx.Response(
                200,
                headers={
                    "Content-Type":
                    "text/html"
                },
                text=article_html,
                request=request,
            )

        return httpx.Response(
            200,
            headers={
                "Content-Type":
                "text/html"
            },
            text="<html>not a pdf</html>",
            request=request,
        )

    transport = httpx.MockTransport(
        handler
    )

    with (
        BuildingSimulationPdfClient(
            transport=transport
        ) as client,
        pytest.raises(
            BuildingSimulationPdfContentError
        ),
    ):
        client.fetch_pdf(
            DOI
        )


def test_article_page_http_error():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            403,
            headers={
                "Content-Type":
                "text/html"
            },
            text="Forbidden",
            request=request,
        )

    transport = httpx.MockTransport(
        handler
    )

    with (
        BuildingSimulationPdfClient(
            transport=transport
        ) as client,
        pytest.raises(
            BuildingSimulationPdfHTTPError
        ),
    ):
        client.fetch_pdf(
            DOI
        )