import pytest

from paperflow.parsers.elsevier_xml import (
    ElsevierXMLValidationError,
    inspect_elsevier_xml,
    require_full_text_xml,
)


def make_full_xml() -> bytes:
    paragraphs_a = "".join(
        f"<ce:para>Introduction paragraph {i}. "
        f"This contains enough scientific text for testing.</ce:para>"
        for i in range(6)
    )

    paragraphs_b = "".join(
        f"<ce:para>Results paragraph {i}. This contains additional scientific content.</ce:para>"
        for i in range(6)
    )

    filler = "A" * 6000

    xml = f"""
    <full-text-retrieval-response
        xmlns:ce="http://www.elsevier.com/xml/common/dtd"
    >
        <ce:sections>
            <ce:section>
                <ce:section-title>
                    Introduction
                </ce:section-title>

                {paragraphs_a}
            </ce:section>

            <ce:section>
                <ce:section-title>
                    Results
                </ce:section-title>

                {paragraphs_b}

                <ce:para>{filler}</ce:para>
            </ce:section>
        </ce:sections>

        <ce:bibliography>
            <ce:bib-reference>
                Reference 1
            </ce:bib-reference>
        </ce:bibliography>
    </full-text-retrieval-response>
    """

    return xml.encode("utf-8")


def test_full_text_xml_passes():
    stats = inspect_elsevier_xml(make_full_xml())

    assert stats.root_name == ("full-text-retrieval-response")

    assert stats.section_count == 2
    assert stats.paragraph_count == 13
    assert stats.reference_count == 1
    assert stats.is_full_text is True


def test_require_full_text_xml():
    stats = require_full_text_xml(make_full_xml())

    assert stats.is_full_text is True


def test_metadata_like_xml_rejected():
    xml = b"""
    <full-text-retrieval-response>
        <coredata>
            <title>Only metadata</title>
        </coredata>
    </full-text-retrieval-response>
    """

    stats = inspect_elsevier_xml(xml)

    assert stats.is_full_text is False

    with pytest.raises(ElsevierXMLValidationError):
        require_full_text_xml(xml)


def test_invalid_xml_rejected():
    with pytest.raises(ElsevierXMLValidationError):
        inspect_elsevier_xml(b"<broken>")
