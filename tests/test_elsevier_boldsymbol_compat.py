from paperflow.cleaners.elsevier_md import clean_elsevier_markdown


def test_elsevier_table_normalizes_boldsymbol_latin_variable():
    markdown = r"""**Table 2** Design variables.

| Variable | Description |
| --- | --- |
| $\boldsymbol{x}_1$ | Balcony size |
| $\boldsymbol{x}_9$ | SHGC |
"""

    cleaned, _ = clean_elsevier_markdown(markdown, b"<root/>")

    assert r"$\mathbf{x}_1$" in cleaned
    assert r"$\mathbf{x}_9$" in cleaned
    assert r"\boldsymbol" not in cleaned


def test_elsevier_table_does_not_rewrite_complex_boldsymbol_expression():
    markdown = r"""| Variable |
| --- |
| $\boldsymbol{\alpha}$ |
"""

    cleaned, _ = clean_elsevier_markdown(markdown, b"<root/>")

    assert r"$\boldsymbol{\alpha}$" in cleaned
