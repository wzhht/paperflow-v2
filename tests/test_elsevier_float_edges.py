from paperflow.cleaners.elsevier_md import clean_elsevier_markdown


def test_inline_table_anchor_is_not_reported_missing():
    markdown = """Paragraph [Table 5](#tbl0005) . <a id="fig0009"></a>\n**Fig. 9** Figure caption. <a id="tbl0005"></a>\n**Table 5** Summary of design strategies.\n\n|  | Cooling load | Comfort hours |\n| --- | --- | --- |\n| Base Case | *1634* | *496* |\n| Scenario 1 | *546* | *671* |\n\n## References\n"""

    xml = b"""\n    <root xmlns:ce="urn:test">\n      <ce:para>\n        <ce:cross-ref refid="tbl0005">Table 5</ce:cross-ref>\n        <ce:float-anchor refid="tbl0005"/>\n      </ce:para>\n      <ce:table id="tbl0005">\n        <tgroup cols="3">\n          <tbody>\n            <row>\n              <entry>Base Case</entry>\n              <entry>1634</entry>\n              <entry>496</entry>\n            </row>\n          </tbody>\n        </tgroup>\n      </ce:table>\n    </root>\n    """

    cleaned, stats = clean_elsevier_markdown(markdown, xml)

    assert stats.missing_float_table_ids == ()
    assert stats.image_only_float_table_ids == ()
    assert stats.table_count_markdown == 1
    assert "**Fig. 9** Figure caption." in cleaned
    assert '<a id="tbl0005"></a>' in cleaned
    assert "| Base Case | 1634 | 496 |" in cleaned
    assert "| Scenario 1 | 546 | 671 |" in cleaned


def test_external_image_only_table_is_warning_class_not_missing():
    markdown = """Paragraph [Table 1](#tbl1).\n\n<a id="tbl1"></a>\n**Table 1** Caption only.\n\n## References\n"""

    xml = b"""\n    <root xmlns:ce="urn:test">\n      <ce:para>\n        <ce:float-anchor refid="tbl1"/>\n      </ce:para>\n      <ce:table id="tbl1">\n        <ce:caption>Caption only</ce:caption>\n        <ce:link locator="fx1001"/>\n      </ce:table>\n    </root>\n    """

    _, stats = clean_elsevier_markdown(markdown, xml)

    assert stats.missing_float_table_ids == ()
    assert stats.image_only_float_table_ids == ("tbl1",)


def test_structured_table_that_is_absent_from_markdown_remains_missing():
    markdown = """Paragraph [Table 2](#tbl2).\n\n## References\n"""

    xml = b"""\n    <root xmlns:ce="urn:test">\n      <ce:para>\n        <ce:float-anchor refid="tbl2"/>\n      </ce:para>\n      <ce:table id="tbl2">\n        <tgroup cols="2">\n          <tbody>\n            <row>\n              <entry>A</entry>\n              <entry>123.45</entry>\n            </row>\n          </tbody>\n        </tgroup>\n      </ce:table>\n    </root>\n    """

    _, stats = clean_elsevier_markdown(markdown, xml)

    assert stats.missing_float_table_ids == ("tbl2",)
    assert stats.image_only_float_table_ids == ()
