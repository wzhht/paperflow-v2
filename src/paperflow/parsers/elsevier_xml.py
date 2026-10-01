from dataclasses import dataclass
from pathlib import Path

import litdown
from lxml import etree


class ElsevierXMLValidationError(RuntimeError):
    """Elsevier XML could not be parsed or does not look like full text."""


@dataclass(frozen=True)
class ElsevierXMLStats:
    root_name: str
    section_count: int
    paragraph_count: int
    reference_count: int
    text_characters: int
    is_full_text: bool
    reason: str


def inspect_elsevier_xml(
    xml_content: bytes,
) -> ElsevierXMLStats:
    """
    Inspect an Elsevier Article Retrieval XML response.

    This is a semantic completeness check rather than
    a simple HTTP/content-type check.
    """

    try:
        parser = etree.XMLParser(
            recover=False,
            huge_tree=True,
        )

        root = etree.fromstring(
            xml_content,
            parser=parser,
        )

    except etree.XMLSyntaxError as exc:
        raise ElsevierXMLValidationError("Elsevier response is not valid XML.") from exc

    root_name = etree.QName(root).localname

    section_count = len(root.xpath("//*[local-name()='section']"))

    paragraph_count = len(
        root.xpath("//*[local-name()='para' or local-name()='p' or local-name()='simple-para']")
    )

    reference_count = len(root.xpath("//*[local-name()='bib-reference' or local-name()='ref']"))

    text = " ".join(x.strip() for x in root.itertext() if x.strip())

    text_characters = len(text)

    reasons = []

    if root_name != "full-text-retrieval-response":
        reasons.append(f"unexpected root element: {root_name}")

    if section_count < 2:
        reasons.append(f"too few sections: {section_count}")

    if paragraph_count < 10:
        reasons.append(f"too few paragraphs: {paragraph_count}")

    if text_characters < 5000:
        reasons.append(f"too little textual content: {text_characters} chars")

    is_full_text = not reasons

    reason = "Structured full text looks complete." if is_full_text else "; ".join(reasons)

    return ElsevierXMLStats(
        root_name=root_name,
        section_count=section_count,
        paragraph_count=paragraph_count,
        reference_count=reference_count,
        text_characters=text_characters,
        is_full_text=is_full_text,
        reason=reason,
    )


def require_full_text_xml(
    xml_content: bytes,
) -> ElsevierXMLStats:
    """
    Validate that an Elsevier XML response is likely
    to contain structured article full text.
    """

    stats = inspect_elsevier_xml(xml_content)

    if not stats.is_full_text:
        raise ElsevierXMLValidationError(stats.reason)

    return stats


def convert_elsevier_xml_to_markdown(
    xml_path: str | Path,
    output_path: str | Path,
) -> str:
    """
    Convert a validated Elsevier XML file to Markdown
    using litdown.
    """

    xml_path = Path(xml_path)
    output_path = Path(output_path)

    markdown = litdown.convert(str(xml_path))

    output_path.write_text(
        markdown,
        encoding="utf-8",
    )

    return markdown
