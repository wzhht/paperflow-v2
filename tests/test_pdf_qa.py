from io import BytesIO

from pypdf import PdfWriter

from paperflow.qa.pdf import (
    PdfExpectation,
    extract_elsevier_pdf_expectation,
    validate_pdf_bytes,
)


def _make_pdf(
    pages: int,
) -> bytes:
    writer = PdfWriter()

    for _ in range(pages):
        writer.add_blank_page(
            width=612,
            height=792,
        )

    buffer = BytesIO()

    writer.write(buffer)

    return buffer.getvalue()


def test_extracts_elsevier_main_pdf_expectation():
    xml = """
<root xmlns:xocs="urn:xocs">
  <xocs:web-pdf>
    <xocs:attachment-eid>
      1-s2.0-example-supp.pdf
    </xocs:attachment-eid>
    <xocs:filename>
      supplement.pdf
    </xocs:filename>
    <xocs:filesize>
      1000
    </xocs:filesize>
    <xocs:web-pdf-purpose>
      SUPPLEMENT
    </xocs:web-pdf-purpose>
    <xocs:web-pdf-page-count>
      2
    </xocs:web-pdf-page-count>
  </xocs:web-pdf>

  <xocs:web-pdf>
    <xocs:attachment-eid>
      1-s2.0-example-main.pdf
    </xocs:attachment-eid>
    <xocs:filename>
      main.pdf
    </xocs:filename>
    <xocs:filesize>
      11180168
    </xocs:filesize>
    <xocs:web-pdf-purpose>
      MAIN
    </xocs:web-pdf-purpose>
    <xocs:web-pdf-page-count>
      23
    </xocs:web-pdf-page-count>
  </xocs:web-pdf>
</root>
"""

    expectation = extract_elsevier_pdf_expectation(xml)

    assert expectation.attachment_eid == "1-s2.0-example-main.pdf"

    assert expectation.filename == "main.pdf"

    assert expectation.expected_pages == 23

    assert expectation.expected_bytes == 11180168


def test_rejects_non_pdf_content():
    expectation = PdfExpectation(
        attachment_eid=None,
        filename="main.pdf",
        expected_pages=20,
        expected_bytes=1000000,
    )

    result = validate_pdf_bytes(
        b"<service-error>AUTHORIZATION</service-error>",
        expectation,
    )

    assert result.status == "invalid_not_pdf"

    assert result.is_valid is False

    assert result.signature_ok is False


def test_accepts_matching_pdf_page_count():
    pdf_content = _make_pdf(pages=3)

    expectation = PdfExpectation(
        attachment_eid=("1-s2.0-example-main.pdf"),
        filename="main.pdf",
        expected_pages=3,
        expected_bytes=len(pdf_content),
    )

    result = validate_pdf_bytes(
        pdf_content,
        expectation,
    )

    assert result.status == "valid"

    assert result.is_valid is True

    assert result.parseable is True

    assert result.actual_pages == 3

    assert result.expected_pages == 3

    assert result.pages_match_expected is True


def test_rejects_one_page_placeholder():
    pdf_content = _make_pdf(pages=1)

    expectation = PdfExpectation(
        attachment_eid=("1-s2.0-example-main.pdf"),
        filename="main.pdf",
        expected_pages=23,
        expected_bytes=11180168,
    )

    result = validate_pdf_bytes(
        pdf_content,
        expectation,
    )

    assert result.status == "invalid_page_count"

    assert result.is_valid is False

    assert result.actual_pages == 1

    assert result.expected_pages == 23

    assert result.pages_match_expected is False


def test_returns_candidate_without_xml_page_count():
    pdf_content = _make_pdf(pages=5)

    result = validate_pdf_bytes(pdf_content)

    assert result.status == "candidate"

    assert result.is_valid is False

    assert result.parseable is True

    assert result.actual_pages == 5

    assert result.expected_pages is None

    assert result.pages_match_expected is None
