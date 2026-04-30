import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from gui import PyBibCVApp, build_app
from src.check_ops import CheckReport
from src.gui_controller import GUIController
from src.import_ops import DOIImportError


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

TEST_TEMPLATE = r"""\documentclass{article}
\begin{document}
\section*{Publications}
\CVList[collection=publications, sort=year_desc, list=enumerate, format="<<author>>, <<year>>: <<title>>, <<journal>>, <<booktitle>>"]
\section*{Talks}
\CVList[collection=talks, sort=year_desc, list=itemize, format="<<title>>, <<note>>, <<year>>"]
\end{document}
"""

PUBLICATIONS_BIB = """@article{smith2024paper,
  title = {Existing Publication},
  author = {Jane Smith},
  year = {2024},
  journal = {Example Journal},
}
"""

TALKS_BIB = """@misc{talk2026,
  title = {Existing Talk},
  author = {Taylor Speaker},
  date = {2026-05-14},
  venue = {Sample Meeting},
}
"""


class GUIControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name)
        (self.root_dir / "data").mkdir()
        (self.root_dir / "templates").mkdir()
        (self.root_dir / "output").mkdir()
        (self.root_dir / "config.json").write_text(TEST_CONFIG, encoding="utf-8")
        (self.root_dir / "templates" / "basic_cv.tex").write_text(TEST_TEMPLATE, encoding="utf-8")
        (self.root_dir / "data" / "publications.bib").write_text(PUBLICATIONS_BIB, encoding="utf-8")
        (self.root_dir / "data" / "talks.bib").write_text(TALKS_BIB, encoding="utf-8")
        (self.root_dir / "data" / "service.bib").write_text("", encoding="utf-8")
        (self.root_dir / "data" / "grants.bib").write_text("", encoding="utf-8")
        (self.root_dir / "data" / "students.bib").write_text("", encoding="utf-8")

        self.controller = GUIController.from_root_dir(self.root_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_gui_entry_point_builds_controller_and_app_wiring(self) -> None:
        fake_root = object()
        fake_app = object()
        with mock.patch("gui.tk.Tk", return_value=fake_root) as tk_ctor, mock.patch(
            "gui.PyBibCVApp", return_value=fake_app
        ) as app_ctor:
            root, app = build_app(self.root_dir)

        self.assertIs(root, fake_root)
        self.assertIs(app, fake_app)
        tk_ctor.assert_called_once()
        app_ctor.assert_called_once()

    def test_gui_no_longer_exposes_validate_or_normalize_actions(self) -> None:
        self.assertFalse(hasattr(PyBibCVApp, "run_validation"))
        self.assertFalse(hasattr(PyBibCVApp, "run_normalization"))

    def test_add_and_edit_through_gui_connected_logic(self) -> None:
        added = self.controller.add_entry(
            "talks",
            {
                "entry_type": "misc",
                "cite_key": "newtalk",
                "title": "New GUI Talk",
                "author": "Jordan GUI",
                "year": "2026",
            },
        )
        edited = self.controller.edit_entry("talks", added["cite_key"], {"note": "Updated via controller"}, [])

        self.assertEqual(edited["fields"]["note"], "Updated via controller")

    def test_import_doi_through_gui_connected_logic(self) -> None:
        try:
            imported = self.controller.import_doi("publications", "10.1038/nphys1170")
        except DOIImportError as exc:
            self.skipTest(f"Network DOI lookup unavailable: {exc}")
            return

        self.assertIn("doi", imported["fields"])
        self.assertTrue(imported["fields"]["title"])

    def test_controller_exposes_required_fields_and_known_entry_types(self) -> None:
        self.assertEqual(
            self.controller.required_fields("talks"),
            ["entry_type", "cite_key", "title", "author", "year"],
        )
        self.assertEqual(self.controller.known_entry_types("talks"), ["misc"])

    def test_import_bibtex_through_gui_connected_logic(self) -> None:
        imported = self.controller.import_bibtex_string(
            "publications",
            "@article{guiimport, title={GUI Imported Paper}, author={Doe, John}, year={2025}}",
        )

        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["cite_key"], "guiimport")

    def test_check_through_gui_connected_logic(self) -> None:
        report = self.controller.check()
        self.assertIn("talks entry 1: missing required field 'year'", "\n".join(report.data_validity_errors))
        self.assertTrue(report.template_coverage_warnings)

    def test_rendering_through_gui_connected_logic(self) -> None:
        result = self.controller.render(output_name="gui_controller_cv", compile_pdf=False)
        self.assertTrue(result.tex_path.exists())

    def test_output_helper_appends_and_clears_text(self) -> None:
        class FakeText:
            def __init__(self) -> None:
                self.contents = ""

            def config(self, **kwargs: str) -> None:
                return None

            def insert(self, index: str, text: str) -> None:
                self.contents += text

            def see(self, index: str) -> None:
                return None

            def delete(self, start: str, end: str) -> None:
                self.contents = ""

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.output_text = FakeText()

        app.write_output("First line")
        app.write_output("Second line")
        self.assertIn("First line\nSecond line\n", app.output_text.contents)

        app.clear_output()
        self.assertEqual(app.output_text.contents, "")

    def test_render_output_includes_compilation_transcript(self) -> None:
        class FakeText:
            def __init__(self) -> None:
                self.contents = ""

            def config(self, **kwargs: str) -> None:
                return None

            def insert(self, index: str, text: str) -> None:
                self.contents += text

            def see(self, index: str) -> None:
                return None

            def delete(self, start: str, end: str) -> None:
                self.contents = ""

        fake_result = SimpleNamespace(
            tex_path=Path("/tmp/example.tex"),
            pdf_path=Path("/tmp/example.pdf"),
            compilation_message="PDF compilation succeeded using xelatex.",
            compilation_log="$ xelatex -interaction=nonstopmode -halt-on-error example.tex\nThis is XeTeX",
        )

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.root = object()
        app.controller = mock.Mock()
        app.controller.render.return_value = fake_result
        app.output_text = FakeText()

        with mock.patch("gui.simpledialog.askstring", return_value="example"), mock.patch(
            "gui.messagebox.askyesno",
            return_value=True,
        ):
            app.render_cv()

        self.assertIn("LaTeX Compilation Output:\n", app.output_text.contents)
        self.assertIn("$ xelatex -interaction=nonstopmode -halt-on-error example.tex\n", app.output_text.contents)
        self.assertIn("This is XeTeX\n", app.output_text.contents)
        self.assertIn("Render Complete:\n", app.output_text.contents)

    def test_check_output_writes_sectioned_results(self) -> None:
        class FakeText:
            def __init__(self) -> None:
                self.contents = ""

            def config(self, **kwargs: str) -> None:
                return None

            def insert(self, index: str, text: str) -> None:
                self.contents += text

            def see(self, index: str) -> None:
                return None

            def delete(self, start: str, end: str) -> None:
                self.contents = ""

        fake_report = CheckReport(
            configuration_issues=["Missing template file"],
            data_validity_errors=["publications entry 1: missing required field 'year'"],
            data_quality_warnings=["Duplicate title 'X' found in 'a' and 'b' in 'publications'."],
            template_coverage_warnings=["Template 'basic_cv.tex' collection 'publications' entry 'a' is missing format field(s): doi."],
        )

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.controller = mock.Mock()
        app.controller.check.return_value = fake_report
        app.output_text = FakeText()

        app.run_check()

        self.assertIn("Configuration issues:\n", app.output_text.contents)
        self.assertIn("Data validity errors:\n", app.output_text.contents)
        self.assertIn("Data quality warnings:\n", app.output_text.contents)
        self.assertIn("Template coverage warnings:\n", app.output_text.contents)


if __name__ == "__main__":
    unittest.main()
