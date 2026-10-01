import json

import httpx
import pytest

from paperflow.sources.elsevier import (
    ElsevierClient,
    ElsevierContentError,
    ElsevierHTTPError,
    ElsevierNetworkError,
)

TEST_DOI = "10.1016/j.buildenv.2025.113229"


def test_fetch_metadata():
    def handler(request):
        assert request.headers["X-ELS-APIKey"] == "test-key"

        assert request.headers["Accept"] == "application/json"

        data = {"full-text-retrieval-response": {"coredata": {"dc:title": "Test article"}}}

        return httpx.Response(
            200,
            content=json.dumps(data).encode(),
            headers={"Content-Type": ("application/json")},
        )

    transport = httpx.MockTransport(handler)

    with ElsevierClient(
        api_key="test-key",
        transport=transport,
    ) as client:
        result = client.fetch_metadata(TEST_DOI)

    assert result["full-text-retrieval-response"]["coredata"]["dc:title"] == "Test article"


def test_fetch_xml_has_no_full_view():
    def handler(request):
        assert request.headers["Accept"] == "text/xml"

        assert request.url.params.get("view") is None

        return httpx.Response(
            200,
            content=(b"<full-text-retrieval-response><coredata /></full-text-retrieval-response>"),
            headers={"Content-Type": "text/xml"},
        )

    transport = httpx.MockTransport(handler)

    with ElsevierClient(
        api_key="test-key",
        transport=transport,
    ) as client:
        xml = client.fetch_xml(TEST_DOI)

    assert xml.startswith(b"<full-text-retrieval-response>")


def test_fetch_pdf_uses_full_view():
    def handler(request):
        assert request.headers["Accept"] == "application/pdf"

        assert request.url.params["view"] == "FULL"

        return httpx.Response(
            200,
            content=b"%PDF-1.7 test",
            headers={"Content-Type": ("application/pdf")},
        )

    transport = httpx.MockTransport(handler)

    with ElsevierClient(
        api_key="test-key",
        transport=transport,
    ) as client:
        pdf = client.fetch_pdf(TEST_DOI)

    assert pdf.startswith(b"%PDF-")


def test_http_error():
    def handler(request):
        return httpx.Response(
            401,
            content=b"Unauthorized",
        )

    transport = httpx.MockTransport(handler)

    with (
        ElsevierClient(
            api_key="bad-key",
            transport=transport,
        ) as client,
        pytest.raises(ElsevierHTTPError),
    ):
        client.fetch_xml(TEST_DOI)


def test_invalid_pdf_rejected():
    def handler(request):
        return httpx.Response(
            200,
            content=(b"<html>Not a PDF</html>"),
        )

    transport = httpx.MockTransport(handler)

    with (
        ElsevierClient(
            api_key="test-key",
            transport=transport,
        ) as client,
        pytest.raises(ElsevierContentError),
    ):
        client.fetch_pdf(TEST_DOI)


def test_network_error_is_retried_and_wrapped():
    attempts = 0

    def handler(request):
        nonlocal attempts

        attempts += 1

        raise httpx.ConnectTimeout(
            "TLS handshake timed out",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with (
        ElsevierClient(
            api_key="test-key",
            transport=transport,
        ) as client,
        pytest.raises(ElsevierNetworkError),
    ):
        client.fetch_metadata(TEST_DOI)

    assert attempts == 3
