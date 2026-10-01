from pathlib import Path

from paperflow.cleaners.elsevier_md import (
    clean_elsevier_markdown,
    clean_elsevier_markdown_file,
)


def test_removes_display_math_and_preserves_values():
    markdown = """
## 3 Methods

SHGC = 0.75 and U-value = 0.5 W/m2K.

<a id="e0005"></a>
$$
P\\left(a<X<b\\right)=1
$$  (1)

## 5 Results

The result was 100 kWh/m2.

## 6 Conclusion

Done.

## References

<a id="b0005"></a>
[1] Example.
"""

    cleaned, stats = clean_elsevier_markdown(
        markdown,
        "<root/>",
    )

    assert "$$" not in cleaned
    assert "P\\left" not in cleaned

    assert "SHGC = 0.75" in cleaned

    assert "U-value = 0.5 W/m2K" in cleaned

    assert "100 kWh/m2" in cleaned

    assert stats.display_equations_removed == 1

    assert stats.remaining_display_math == 0

    assert stats.has_results is True

    assert stats.has_conclusion is True

    assert stats.has_references is True


def test_relocates_float_table_after_reference():
    xml = """
<root xmlns:ce="urn:ce">
  <ce:para>
    <ce:float-anchor refid="t0025"/>
  </ce:para>
</root>
"""

    markdown = """
## 4 UBEM

The versions are shown in [Table 5](#t0025) .

Next paragraph.

## References

<a id="b0005"></a>
[1] Example.

<a id="t0025"></a>
**Table 5** Semantic data.

| Parameter | Value |
| --- | --- |
| WWR | 0.2 |

*Note: example.*
"""

    cleaned, stats = clean_elsevier_markdown(
        markdown,
        xml,
    )

    table_position = cleaned.find('<a id="t0025"></a>')

    next_paragraph_position = cleaned.find("Next paragraph.")

    references_position = cleaned.find("## References")

    assert table_position != -1

    assert table_position < next_paragraph_position

    assert table_position < references_position

    assert stats.relocated_table_ids == ("t0025",)

    assert stats.missing_float_table_ids == ()


def test_keeps_correct_float_table_in_place():
    xml = """
<root xmlns:ce="urn:ce">
  <ce:float-anchor refid="t0005"/>
</root>
"""

    markdown = """
## 1 Introduction

Shown in [Table 1](#t0005) .

<a id="t0005"></a>
**Table 1** Example.

| A | B |
| --- | --- |
| 1 | 2 |

Next paragraph.

## References
"""

    cleaned, stats = clean_elsevier_markdown(
        markdown,
        xml,
    )

    assert cleaned.count('<a id="t0005"></a>') == 1

    assert stats.relocated_table_ids == ()

    assert stats.missing_float_table_ids == ()


def test_reports_missing_float_table():
    xml = """
<root xmlns:ce="urn:ce">
  <ce:float-anchor refid="t0099"/>
</root>
"""

    markdown = """
## 5 Results

No table was converted.

## 6 Conclusion

Done.

## References
"""

    _, stats = clean_elsevier_markdown(
        markdown,
        xml,
    )

    assert stats.float_table_ids == ("t0099",)

    assert stats.missing_float_table_ids == ("t0099",)


def test_clean_elsevier_markdown_file(
    tmp_path: Path,
):
    raw_path = tmp_path / "paper_raw.md"

    xml_path = tmp_path / "paper.xml"

    output_path = tmp_path / "paper_llm.md"

    raw_path.write_text(
        """
## 5 Results

Value = 42.

$$
x = 1
$$  (1)

## 6 Conclusion

Done.

## References
""",
        encoding="utf-8",
    )

    xml_path.write_text(
        "<root/>",
        encoding="utf-8",
    )

    stats = clean_elsevier_markdown_file(
        raw_path,
        xml_path,
        output_path,
    )

    output = output_path.read_text(encoding="utf-8")

    assert output_path.exists()

    assert "$$" not in output

    assert "Value = 42." in output

    assert stats.display_equations_removed == 1


def test_normalizes_table_emphasis():
    markdown = r"""
## 5 Results

| **\*\*kWh/m2 \*\*** | **VBASELINE** |
| --- | --- |
| \*QConduction \* | -70.42 |
| \*QHeating \* | 84.63 |

## 6 Conclusion

Done.

## References
"""

    cleaned, _ = clean_elsevier_markdown(
        markdown,
        "<root/>",
    )

    assert "| kWh/m2 | VBASELINE |" in cleaned

    assert "| QConduction | -70.42 |" in cleaned

    assert "| QHeating | 84.63 |" in cleaned

    assert r"\*" not in cleaned


def test_preserves_significance_stars():
    markdown = """
## 5 Results

| Variable | Value |
| --- | --- |
| Coefficient | 0.35* |
| Estimate | 0.21** |

## 6 Conclusion

Done.

## References
"""

    cleaned, _ = clean_elsevier_markdown(
        markdown,
        "<root/>",
    )

    assert "0.35*" in cleaned

    assert "0.21**" in cleaned


def test_normalizes_non_breaking_spaces():
    markdown = """
## 5 Results

| Parameter | Value |
| --- | --- |
| **U-value** | 0.5\u00a0W/m2K |
| **SHGC** | 0.75 |

## 6 Conclusion

Done.

## References
"""

    cleaned, _ = clean_elsevier_markdown(
        markdown,
        "<root/>",
    )

    assert "\u00a0" not in cleaned

    assert "| U-value | 0.5 W/m2K |" in cleaned

    assert "| SHGC | 0.75 |" in cleaned


def test_normalizes_multiple_emphasis_fragments_in_cell():
    markdown = r"""
## 5 Results

| <br>**VBASELINE \*\* / \*\*QH** | **IOD** | **GWP** |
| --- | --- | --- |
| Μ | 99.57 | 0.20 |
| std | 41.30 | 0.10 |

## 6 Conclusion

Done.

## References
"""

    cleaned, _ = clean_elsevier_markdown(
        markdown,
        "<root/>",
    )

    assert "| VBASELINE / QH | IOD | GWP |" in cleaned

    assert r"\*" not in cleaned

    assert "<br>" not in cleaned


def test_keeps_table_numeric_values_unchanged():
    markdown = r"""
## 5 Results

| <br>**VBASELINE \*\* / \*\*QH** | **IOD** | **GWP** |
| --- | --- | --- |
| Μ | 99.57 | 0.20 |
| std | 41.30 | 0.10 |
| min | 22.02 | 0.00 |
| max | 305.5 | 0.57 |
| Change | − | − |

## 6 Conclusion

Done.

## References
"""

    cleaned, _ = clean_elsevier_markdown(
        markdown,
        "<root/>",
    )

    assert "99.57" in cleaned

    assert "0.20" in cleaned

    assert "41.30" in cleaned

    assert "22.02" in cleaned

    assert "305.5" in cleaned

    assert "| Change | − | − |" in cleaned
