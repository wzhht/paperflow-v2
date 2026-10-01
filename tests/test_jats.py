from paperflow.parsers.jats import (
    convert_jats_xml_to_markdown,
)
from paperflow.qa.structured import (
    audit_jats_table_numeric_values,
    inspect_jats_xml,
)


def _write_synthetic_jats(tmp_path):
    long_sentence = (
        "This synthetic paragraph represents complete scientific body text for parser "
        "validation. It discusses building thermal resilience, SHGC, U-value, WWR, "
        "cooling load, operative temperature, recovery time, and future climate "
        "conditions while containing no text copied from a published article. "
    )

    sections = []

    for title in (
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
    ):
        paragraphs = "".join(
            f"<p>{long_sentence * 3} Section {title}, synthetic paragraph {index}.</p>"
            for index in range(1, 4)
        )

        extra = ""

        if title == "Results":
            extra = """
            <table-wrap id="t1">
              <label>Table 1</label>
              <caption>
                <p>Synthetic thermal performance results.</p>
              </caption>
              <table>
                <thead>
                  <tr>
                    <th>Period</th>
                    <th>CL</th>
                    <th>Tmax</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Historical</td>
                    <td>18.5</td>
                    <td>31.4</td>
                  </tr>
                  <tr>
                    <td>Future</td>
                    <td>23.4</td>
                    <td>32.3</td>
                  </tr>
                </tbody>
              </table>
            </table-wrap>

            <table-wrap id="t2">
              <label>Table 2</label>
              <caption>
                <p>Synthetic design variables.</p>
              </caption>
              <table>
                <thead>
                  <tr>
                    <th>Variable</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>SHGC</td>
                    <td>0.29</td>
                  </tr>
                  <tr>
                    <td>Roof U-value</td>
                    <td>0.35</td>
                  </tr>
                  <tr>
                    <td>Roof TC</td>
                    <td>790</td>
                  </tr>
                </tbody>
              </table>
            </table-wrap>

            <fig id="f1">
              <label>Fig. 1</label>
              <caption>
                <p>Synthetic workflow figure caption.</p>
              </caption>
              <graphic
                xmlns:xlink="http://www.w3.org/1999/xlink"
                xlink:href="synthetic_figure.png"
              />
            </fig>
            """

        sections.append(
            f"""
            <sec>
              <title>{title}</title>
              {paragraphs}
              {extra}
            </sec>
            """
        )

    references = "".join(
        f"""
        <ref id="r{index}">
          <label>{index}</label>
          <mixed-citation>
            Example Author {index}. Synthetic reference {index}. Test Journal. 2026.
          </mixed-citation>
        </ref>
        """
        for index in range(1, 6)
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-title-group>
        <journal-title>PaperFlow Synthetic Test Journal</journal-title>
      </journal-title-group>
    </journal-meta>

    <article-meta>
      <article-id pub-id-type="doi">10.1000/paperflow.synthetic.jats</article-id>

      <title-group>
        <article-title>Synthetic climate resilience study</article-title>
      </title-group>

      <contrib-group>
        <contrib contrib-type="author">
          <name>
            <surname>Example</surname>
            <given-names>Alice</given-names>
          </name>
        </contrib>
      </contrib-group>

      <pub-date date-type="pub">
        <day>1</day>
        <month>10</month>
        <year>2026</year>
      </pub-date>

      <abstract>
        <p>
          Synthetic abstract for PaperFlow parser regression tests.
          No published-paper prose is included in this fixture.
        </p>
      </abstract>
    </article-meta>
  </front>

  <body>
    {''.join(sections)}
  </body>

  <back>
    <ref-list>
      {references}
    </ref-list>
  </back>
</article>
"""

    path = tmp_path / "synthetic_jats.xml"
    path.write_text(xml, encoding="utf-8")

    return path


def test_synthetic_jats_is_full_text_candidate(tmp_path):
    fixture = _write_synthetic_jats(tmp_path)

    stats = inspect_jats_xml(fixture)

    assert stats.doi == "10.1000/paperflow.synthetic.jats"
    assert stats.has_body is True

    assert stats.section_count >= 4
    assert stats.paragraph_count >= 12
    assert stats.reference_count == 5
    assert stats.table_count == 2
    assert stats.figure_count == 1

    assert stats.body_characters >= 5000
    assert stats.candidate_full_text is True


def test_synthetic_jats_renders_llm_markdown(tmp_path):
    fixture = _write_synthetic_jats(tmp_path)

    output = tmp_path / "paper.md"

    markdown = convert_jats_xml_to_markdown(
        fixture,
        output,
    )

    assert output.read_text(encoding="utf-8") == markdown

    assert "# Synthetic climate resilience study" in markdown

    assert "## Introduction" in markdown
    assert "## Methods" in markdown
    assert "## Results" in markdown
    assert "## Discussion" in markdown
    assert "## References" in markdown

    assert "**Table 1.**" in markdown
    assert "**Table 2.**" in markdown

    assert "18.5" in markdown
    assert "31.4" in markdown
    assert "23.4" in markdown
    assert "32.3" in markdown

    assert "SHGC" in markdown
    assert "0.29" in markdown
    assert "0.35" in markdown
    assert "790" in markdown

    assert "Synthetic workflow figure caption." in markdown

    assert "Example Author 1." in markdown
    assert "Synthetic reference 5." in markdown

    assert "synthetic_figure.png" not in markdown
    assert "![" not in markdown

    assert "$$" not in markdown
    assert "```math" not in markdown


def test_synthetic_jats_table_numbers_are_exact(tmp_path):
    fixture = _write_synthetic_jats(tmp_path)

    output = tmp_path / "paper.md"

    markdown = convert_jats_xml_to_markdown(
        fixture,
        output,
    )

    audit = audit_jats_table_numeric_values(
        fixture,
        markdown,
    )

    assert audit.values_match is True
    assert audit.markdown_tokens == audit.source_tokens

    for token in (
        "18.5",
        "31.4",
        "23.4",
        "32.3",
        "0.29",
        "0.35",
        "790",
    ):
        assert token in audit.source_tokens
