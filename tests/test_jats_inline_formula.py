from __future__ import annotations

from paperflow.parsers.jats import convert_jats_xml_to_markdown


def test_springer_inline_tex_math_drops_latex_wrapper_and_avoids_duplicates(
    tmp_path,
):
    xml = r"""<article xmlns:mml="http://www.w3.org/1998/Math/MathML">
  <front>
    <article-meta>
      <title-group>
        <article-title>Inline formula demo</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Methods</title>
      <p>The flux (<inline-formula><alternatives>
        <mml:math>
          <mml:msubsup>
            <mml:mi>F</mml:mi>
            <mml:mi>vent</mml:mi>
            <mml:mi>t</mml:mi>
          </mml:msubsup>
        </mml:math>
        <tex-math>\documentclass[12pt]{minimal} \usepackage{amsmath} \usepackage{wasysym} \setlength{\oddsidemargin}{-69pt} \begin{document}$${{F}_{{\rm{vent}}}}^{t}$$\end{document}</tex-math>
      </alternatives></inline-formula>) considers only sensible heat exchanges.</p>
    </sec>
  </body>
</article>"""

    input_path = tmp_path / "paper.jats.xml"
    output_path = tmp_path / "paper_llm.md"
    input_path.write_text(xml, encoding="utf-8")

    markdown = convert_jats_xml_to_markdown(
        input_path,
        output_path,
    )

    assert "${{F}_{{\\rm{vent}}}}^{t}$" in markdown
    assert "Fventt" not in markdown
    assert "\\documentclass" not in markdown
    assert "\\usepackage" not in markdown
    assert "\\begin{document}" not in markdown
    assert "\\end{document}" not in markdown


def test_springer_inline_variables_are_preserved_once(tmp_path):
    xml = r"""<article xmlns:mml="http://www.w3.org/1998/Math/MathML">
  <front>
    <article-meta>
      <title-group>
        <article-title>Variable demo</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Methods</title>
      <p>Heating and cooling service demand for year <inline-formula><alternatives><mml:math><mml:mi>y</mml:mi></mml:math><tex-math>\documentclass{minimal}\begin{document}$$y$$\end{document}</tex-math></alternatives></inline-formula>, region <inline-formula><tex-math>\documentclass{minimal}\begin{document}$$r$$\end{document}</tex-math></inline-formula>, and technology <inline-formula><tex-math>\documentclass{minimal}\begin{document}$$i$$\end{document}</tex-math></inline-formula> is represented below.</p>
      <p>where <inline-formula><tex-math>\documentclass{minimal}\begin{document}$${HDD}$$\end{document}</tex-math></inline-formula> and <inline-formula><tex-math>\documentclass{minimal}\begin{document}$${CDD}$$\end{document}</tex-math></inline-formula> are degree days; <inline-formula><tex-math>\documentclass{minimal}\begin{document}$$\eta$$\end{document}</tex-math></inline-formula> is conductance.</p>
    </sec>
  </body>
</article>"""

    input_path = tmp_path / "paper.jats.xml"
    output_path = tmp_path / "paper_llm.md"
    input_path.write_text(xml, encoding="utf-8")

    markdown = convert_jats_xml_to_markdown(
        input_path,
        output_path,
    )

    assert markdown.count("$y$") == 1
    assert markdown.count("$r$") == 1
    assert markdown.count("$i$") == 1
    assert markdown.count("${HDD}$") == 1
    assert markdown.count("${CDD}$") == 1
    assert markdown.count("$\\eta$") == 1
    assert "\\documentclass" not in markdown


def test_display_formula_remains_omitted(tmp_path):
    xml = r"""<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Display formula demo</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Methods</title>
      <p>Before the equation.</p>
      <disp-formula id="eq1">
        <tex-math>\documentclass{minimal}\begin{document}$$x=y+1$$\end{document}</tex-math>
      </disp-formula>
      <p>After the equation.</p>
    </sec>
  </body>
</article>"""

    input_path = tmp_path / "paper.jats.xml"
    output_path = tmp_path / "paper_llm.md"
    input_path.write_text(xml, encoding="utf-8")

    markdown = convert_jats_xml_to_markdown(
        input_path,
        output_path,
    )

    assert "Before the equation." in markdown
    assert "After the equation." in markdown
    assert "x=y+1" not in markdown
    assert "\\documentclass" not in markdown
