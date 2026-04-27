import tempfile
import unittest
from unittest import mock
from pathlib import Path

from src.bibtex_ops import BibTeXManager
from src.render_ops import CVRenderer


TEST_CONFIG = """{
  "categories": {
    "publications": "data/publications.bib",
    "talks": "data/talks.bib",
    "service": "data/service.bib",
    "grants": "data/grants.bib",
    "students": "data/students.bib"
  },
  "required_fields": {
    "publications": ["entry_type", "cite_key", "title", "author", "year"],
    "talks": ["entry_type", "cite_key", "title", "author", "year"],
    "service": ["entry_type", "cite_key", "title", "author", "year"],
    "grants": ["entry_type", "cite_key", "title", "author", "year"],
    "students": ["entry_type", "cite_key", "title", "author", "year"]
  },
  "template_name": "basic_cv",
  "latex_engine": "xelatex",
  "output_dir": "output",
  "author_name": "Sample Academic"
}"""

DIRECTIVE_TEMPLATE = r"""\documentclass{article}
\begin{document}
Introductory free text.
\CVList[collection=publications, select=all, sort=year_desc, limit=2, list=enumerate, format="<<author>>, <<year>>: <<title>>, <<journal>>"]
\CVList[collection=talks, select=after(2024), sort=year, list=itemize, format="<<title>>, <<note>>, <<year>>"]
\CVList[collection=students, select=all, sort=lastname, list=etaremune, format="<<author>>, <<title>>, <<school>>, <<year>>"]
\end{document}
"""

MALFORMED_TEMPLATE = r"""\documentclass{article}
\begin{document}
\CVList[collection=publications, sort=year_desc, list=enumerate, format="<<title>>"
\end{document}
"""

BASIC_TEMPLATE = r"""\documentclass{article}
\begin{document}
<<DOCUMENT_TITLE>>
<<AUTHOR_NAME>>
\section*{Publications}
\CVList[collection=publications, sort=year_desc, list=enumerate, format="<<author>>, <<year>>: <<title>>, <<journal>>"]
\section*{Talks}
\CVList[collection=talks, sort=year_desc, list=itemize, format="<<title>>, <<note>>, <<year>>"]
\section*{Service}
\CVList[collection=service, sort=year_desc, list=itemize, format="<<title>>, <<year>>"]
\section*{Students}
\CVList[collection=students, sort=lastname, list=etaremune, format="<<author>>, <<title>>, <<school>>, <<year>>"]
\end{document}
"""

NSF_TEMPLATE = r"""\documentclass{article}
\begin{document}
Selected outputs only.
\CVList[collection=publications, select=after(2023), sort=year_desc, limit=1, list=enumerate, format="<<title>>, <<year>>"]
Recent talks.
\CVList[collection=talks, select=after(2024), sort=year_desc, limit=1, list=itemize, format="<<title>>, <<year>>"]
\end{document}
"""

PUBLICATIONS_BIB = """@article{doe2024,
  title = {Recent Publication},
  author = {Jane Doe},
  year = {2024},
  journal = {Example Journal},
  top5 = {yes},
}

@article{old2021,
  title = {Older Publication},
  author = {Alex Example},
  year = {2021},
  journal = {Archive Journal},
}
"""

TALKS_BIB = """@misc{talk2025,
  title = {Workflow Talk},
  author = {Sam Speaker},
  year = {2025},
  note = {Research workflow seminar},
}

@misc{talk2023,
  title = {Archived Talk},
  author = {Jamie Speaker},
  year = {2023},
  note = {Older seminar},
}
"""

STUDENTS_BIB = """@phdthesis{student2026,
  title = {Dissertation Title},
  author = {Chris Student},
  year = {2026},
  school = {Example University},
}
"""


class RenderOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "data").mkdir()
        (self.root / "templates").mkdir()
        (self.root / "config.json").write_text(TEST_CONFIG, encoding="utf-8")
        (self.root / "templates" / "directive_test.tex").write_text(DIRECTIVE_TEMPLATE, encoding="utf-8")
        (self.root / "templates" / "malformed.tex").write_text(MALFORMED_TEMPLATE, encoding="utf-8")
        (self.root / "templates" / "basic_cv.tex").write_text(BASIC_TEMPLATE, encoding="utf-8")
        (self.root / "templates" / "nsf_biosketch.tex").write_text(NSF_TEMPLATE, encoding="utf-8")
        (self.root / "data" / "publications.bib").write_text(PUBLICATIONS_BIB, encoding="utf-8")
        (self.root / "data" / "talks.bib").write_text(TALKS_BIB, encoding="utf-8")
        (self.root / "data" / "service.bib").write_text("", encoding="utf-8")
        (self.root / "data" / "grants.bib").write_text("", encoding="utf-8")
        (self.root / "data" / "students.bib").write_text(STUDENTS_BIB, encoding="utf-8")

        self.manager = BibTeXManager(self.root)
        self.manager.ensure_storage()
        self.renderer = CVRenderer(self.root, self.manager)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parsing_valid_cvlist_directive(self) -> None:
        template_text = (self.root / "templates" / "directive_test.tex").read_text(encoding="utf-8")
        directives = self.renderer.parse_directives(template_text)
        self.assertEqual(len(directives), 3)
        self.assertEqual(directives[0].collection, "publications")
        self.assertEqual(directives[0].sort, "year_desc")

    def test_detecting_malformed_directive_syntax(self) -> None:
        template_text = (self.root / "templates" / "malformed.tex").read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            self.renderer.parse_directives(template_text)

    def test_select_all(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=publications, select=all, sort=year_desc, list=enumerate, format="<<title>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertIn("Recent Publication", rendered)
        self.assertIn("Older Publication", rendered)

    def test_select_field_expression(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=publications, select=field(top5,yes), sort=year_desc, list=enumerate, format="<<title>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertIn("Recent Publication", rendered)
        self.assertNotIn("Older Publication", rendered)

    def test_select_after_expression(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=talks, select=after(2024), sort=year_desc, list=itemize, format="<<title>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertIn("Workflow Talk", rendered)
        self.assertNotIn("Archived Talk", rendered)

    def test_sort_year(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=publications, sort=year, list=enumerate, format="<<title>>, <<year>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertLess(rendered.find("Older Publication"), rendered.find("Recent Publication"))

    def test_sort_year_desc(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=publications, sort=year_desc, list=enumerate, format="<<title>>, <<year>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertLess(rendered.find("Recent Publication"), rendered.find("Older Publication"))

    def test_sort_lastname(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=students, sort=lastname, list=etaremune, format="<<author>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertIn("\\begin{etaremune}", rendered)

    def test_limit_behavior(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=publications, sort=year_desc, limit=1, list=enumerate, format="<<title>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertIn("Recent Publication", rendered)
        self.assertNotIn("Older Publication", rendered)

    def test_list_itemize(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=talks, sort=year_desc, list=itemize, format="<<title>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertIn("\\begin{itemize}", rendered)

    def test_list_enumerate(self) -> None:
        directive = self.renderer.parse_directive(
            'collection=publications, sort=year_desc, list=enumerate, format="<<title>>"'
        )
        rendered = self.renderer.render_directive(directive)
        self.assertIn("\\begin{enumerate}", rendered)

    def test_placeholder_substitution_in_format(self) -> None:
        entry = self.manager.list_entries("publications")[0]
        rendered = self.renderer.format_entry(entry, "<<author>>, <<year>>: <<title>>, <<journal>>")
        self.assertIn("Jane Doe", rendered)
        self.assertIn("Recent Publication", rendered)
        self.assertIn("Example Journal", rendered)

    def test_missing_placeholder_field_handled_safely(self) -> None:
        entry = self.manager.list_entries("publications")[0]
        rendered = self.renderer.format_entry(entry, "<<title>>, <<volume>>, <<number>>")
        self.assertIn("Recent Publication", rendered)
        self.assertNotIn("<<", rendered)

    def test_rendering_migrated_basic_template(self) -> None:
        tex_content = self.renderer.render_tex("basic_cv")
        self.assertIn("\\section*{Publications}", tex_content)
        self.assertIn("Recent Publication", tex_content)
        self.assertIn("Workflow Talk", tex_content)

    def test_rendering_new_nsf_style_template(self) -> None:
        tex_content = self.renderer.render_tex("nsf_biosketch")
        self.assertIn("Selected outputs only.", tex_content)
        self.assertIn("Recent Publication", tex_content)
        self.assertNotIn("Older Publication", tex_content)

    def test_template_free_text_remains_unchanged(self) -> None:
        tex_content = self.renderer.render_tex("directive_test")
        self.assertIn("Introductory free text.", tex_content)

    def test_unknown_option_name_fails_clearly(self) -> None:
        with self.assertRaises(ValueError):
            self.renderer.parse_directive(
                'collection=publications, sort=year_desc, list=enumerate, bogus=value, format="<<title>>"'
            )

    def test_invalid_limit_fails_clearly(self) -> None:
        with self.assertRaises(ValueError):
            self.renderer.parse_directive(
                'collection=publications, sort=year_desc, limit=nope, list=enumerate, format="<<title>>"'
            )

    def test_find_latex_compiler_prefers_configured_engine(self) -> None:
        def fake_which(name: str) -> str:
            available = {"xelatex": "/usr/bin/xelatex", "pdflatex": "/usr/bin/pdflatex"}
            return available.get(name, "")

        with mock.patch("src.render_ops.shutil.which", side_effect=fake_which):
            compiler = self.renderer.find_latex_compiler(self.renderer.latex_engine)

        self.assertEqual(compiler, "xelatex")

    def test_compile_pdf_includes_full_command_output_in_log(self) -> None:
        tex_path = self.root / "output" / "compile_me.tex"
        tex_path.parent.mkdir(exist_ok=True)
        tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}", encoding="utf-8")

        completed = mock.Mock(returncode=0, stdout="This is XeTeX\nOutput written on compile_me.pdf", stderr="")
        with mock.patch("src.render_ops.shutil.which", return_value="/usr/bin/xelatex"), mock.patch(
            "src.render_ops.subprocess.run",
            return_value=completed,
        ):
            pdf_path, message, log_output = self.renderer.compile_pdf(tex_path)

        self.assertEqual(pdf_path, tex_path.with_suffix(".pdf"))
        self.assertIn("PDF compilation succeeded using xelatex.", message)
        self.assertIn("$ xelatex -interaction=nonstopmode -halt-on-error compile_me.tex", log_output)
        self.assertIn("This is XeTeX", log_output)


if __name__ == "__main__":
    unittest.main()
