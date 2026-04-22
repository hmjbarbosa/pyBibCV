import tempfile
import unittest
from pathlib import Path

from bibtex_ops import BibTeXManager
from render_ops import CVRenderer


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
  "output_dir": "output",
  "author_name": "Sample Academic"
}"""

TEST_TEMPLATE = r"""\documentclass{article}
\begin{document}
<<DOCUMENT_TITLE>>
<<AUTHOR_NAME>>
<<SECTIONS_CONTENT>>
\end{document}
"""

TEST_TEMPLATE_JSON = """{
  "document_title": "Curriculum Vitae",
  "sections": {
    "Publications": {
      "category": "publications",
      "list": "enumerate",
      "format": "<<author>>, <<year>>: <<title>>, <<journal>>"
    },
    "Talks": {
      "category": "talks",
      "list": "itemize",
      "format": "<<title>>, <<note>>, <<year>>"
    },
    "Service": {
      "category": "service",
      "list": "itemize",
      "format": "<<title>>, <<year>>"
    },
    "Students": {
      "category": "students",
      "list": "reverse-enumerate",
      "format": "<<author>>, <<title>>, <<school>>, <<year>>"
    },
    "Missing": {
      "category": "missing_category",
      "list": "reverse-enumerate",
      "format": "<<title>>, <<year>>"
    }
  }
}"""

PUBLICATIONS_BIB = """@article{doe2024,
  title = {Recent Publication},
  author = {Jane Doe},
  year = {2024},
  journal = {Example Journal},
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
        (self.root / "templates" / "basic_cv.tex").write_text(TEST_TEMPLATE, encoding="utf-8")
        (self.root / "templates" / "basic_cv.json").write_text(TEST_TEMPLATE_JSON, encoding="utf-8")
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

    def test_collect_sections_loads_multiple_bib_files(self) -> None:
        template_spec = self.renderer.load_template_spec("basic_cv")
        sections = self.renderer.collect_sections(template_spec)
        self.assertEqual(len(sections["Publications"]["entries"]), 2)
        self.assertEqual(len(sections["Talks"]["entries"]), 1)
        self.assertEqual(len(sections["Service"]["entries"]), 0)

    def test_filter_entries_by_min_year(self) -> None:
        template_spec = self.renderer.load_template_spec("basic_cv")
        sections = self.renderer.collect_sections(template_spec, min_year=2023)
        self.assertEqual(len(sections["Publications"]["entries"]), 1)
        self.assertEqual(sections["Publications"]["entries"][0]["cite_key"], "doe2024")

    def test_filter_entries_by_keyword(self) -> None:
        template_spec = self.renderer.load_template_spec("basic_cv")
        sections = self.renderer.collect_sections(template_spec, keyword="workflow")
        self.assertEqual(len(sections["Talks"]["entries"]), 1)
        self.assertEqual(len(sections["Publications"]["entries"]), 0)

    def test_render_tex_includes_section_headers_and_entries(self) -> None:
        template_spec = self.renderer.load_template_spec("basic_cv")
        tex_content = self.renderer.render_tex("basic_cv", template_spec, self.renderer.collect_sections(template_spec))
        self.assertIn("Publications", tex_content)
        self.assertIn("Recent Publication", tex_content)
        self.assertIn("No entries available.", tex_content)
        self.assertIn("\\begin{enumerate}", tex_content)
        self.assertIn("\\begin{etaremune}", tex_content)

    def test_collect_sections_handles_missing_category_mapping(self) -> None:
        template_spec = self.renderer.load_template_spec("basic_cv")
        sections = self.renderer.collect_sections(template_spec)
        self.assertEqual(sections["Missing"]["entries"], [])

    def test_format_entry_uses_template_placeholders(self) -> None:
        template_spec = self.renderer.load_template_spec("basic_cv")
        publication_entry = self.manager.list_entries("publications")[0]
        publication_spec = template_spec["sections"]["Publications"]
        rendered = self.renderer.format_entry(publication_entry, publication_spec["format"])
        self.assertIn("Jane Doe", rendered)
        self.assertIn("Recent Publication", rendered)
        self.assertIn("Example Journal", rendered)
        self.assertNotIn("<<", rendered)

    def test_render_writes_tex_file_even_without_pdf_compiler(self) -> None:
        result = self.renderer.render(output_name="test_cv", compile_pdf=False)
        self.assertTrue(result.tex_path.exists())
        self.assertIsNone(result.pdf_path)

    def test_render_uses_template_name_from_config_by_default(self) -> None:
        result = self.renderer.render(output_name="default_template_cv", compile_pdf=False)
        content = result.tex_path.read_text(encoding="utf-8")
        self.assertIn("Curriculum Vitae", content)
        self.assertIn("Publications", content)


if __name__ == "__main__":
    unittest.main()
