import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.bibtex_ops import BibTeXManager
from src.import_ops import DOIImportError, ImportManager
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
  doi = {10.1000/existing.doi},
}
"""

TALKS_BIB = """@misc{barbosa_agu_2026,
  title = {Initial Talk Title},
  author = {Henrique Barbosa},
  venue = {Chicago, IL},
  date = {2026-12-10},
}
"""


class Milestone3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "src").mkdir()
        (self.root / "data").mkdir()
        (self.root / "templates").mkdir()
        (self.root / "output").mkdir()

        project_root = Path(__file__).resolve().parents[1]
        shutil.copy2(project_root / "cli.py", self.root / "cli.py")
        for module_name in ["__init__.py", "bibtex_ops.py", "import_ops.py", "render_ops.py"]:
            shutil.copy2(project_root / "src" / module_name, self.root / "src" / module_name)

        (self.root / "config.json").write_text(TEST_CONFIG, encoding="utf-8")
        (self.root / "templates" / "basic_cv.tex").write_text(TEST_TEMPLATE, encoding="utf-8")
        (self.root / "data" / "publications.bib").write_text(PUBLICATIONS_BIB, encoding="utf-8")
        (self.root / "data" / "talks.bib").write_text(TALKS_BIB, encoding="utf-8")
        (self.root / "data" / "service.bib").write_text("", encoding="utf-8")
        (self.root / "data" / "grants.bib").write_text("", encoding="utf-8")
        (self.root / "data" / "students.bib").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", "cli.py", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_edit_one_field_in_existing_talk_entry(self) -> None:
        completed = self.run_cli("edit", "talks", "barbosa_agu_2026", "--set", "note=Updated Meeting")
        content = (self.root / "data" / "talks.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Updated Meeting", content)

    def test_edit_multiple_fields_in_one_command(self) -> None:
        completed = self.run_cli(
            "edit",
            "talks",
            "barbosa_agu_2026",
            "--set",
            "title=Better Title",
            "--set",
            "presentation_type=poster",
        )
        content = (self.root / "data" / "talks.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Better Title", content)
        self.assertIn("presentation_type = {poster}", content)

    def test_remove_field_from_entry(self) -> None:
        completed = self.run_cli("edit", "talks", "barbosa_agu_2026", "--remove", "venue")
        content = (self.root / "data" / "talks.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("venue =", content)

    def test_show_raw_entry(self) -> None:
        completed = self.run_cli("show", "talks", "barbosa_agu_2026")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("@misc{barbosa_agu_2026,", completed.stdout)
        self.assertIn("title = {Initial Talk Title}", completed.stdout)

    def test_import_publication_from_doi(self) -> None:
        manager = BibTeXManager(self.root)
        importer = ImportManager(manager)
        try:
            imported = importer.import_doi("publications", "10.1038/nphys1170")
        except DOIImportError as exc:
            self.skipTest(f"Network DOI lookup unavailable: {exc}")

        self.assertIn("doi", imported["fields"])
        self.assertTrue(imported["fields"]["title"])

    def test_handle_doi_lookup_failure_gracefully(self) -> None:
        completed = self.run_cli("import-doi", "publications", "10.0000/definitely.invalid.doi")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("DOI lookup failed", completed.stdout)

    def test_import_publication_from_bibtex_file(self) -> None:
        import_file = self.root / "paper.bib"
        import_file.write_text(
            "@article{newpaper, title={Imported File Paper}, author={Doe, John}, year={2025}, doi={10.1000/file.doi}}",
            encoding="utf-8",
        )

        completed = self.run_cli("import-bibtex", "publications", "--file", str(import_file))
        content = (self.root / "data" / "publications.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Imported File Paper", content)

    def test_import_publication_from_bibtex_string(self) -> None:
        completed = self.run_cli(
            "import-bibtex",
            "publications",
            "--string",
            "@article{newstring, title={Imported String Paper}, author={Doe, John}, year={2025}, doi={10.1000/string.doi}}",
        )
        content = (self.root / "data" / "publications.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Imported String Paper", content)

    def test_detect_duplicate_cite_key_during_import(self) -> None:
        completed = self.run_cli(
            "import-bibtex",
            "publications",
            "--string",
            "@article{smith2024paper, title={Second Imported Paper}, author={Doe, John}, year={2025}, doi={10.1000/new.doi}}",
        )
        content = (self.root / "data" / "publications.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("@article{smith2024paper_2,", content)

    def test_detect_duplicate_doi_during_import(self) -> None:
        completed = self.run_cli(
            "import-bibtex",
            "publications",
            "--string",
            "@article{duplicateDoi, title={Second Imported Paper}, author={Doe, John}, year={2025}, doi={10.1000/existing.doi}}",
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Duplicate DOI", completed.stdout)

    def test_normalize_collection_in_dry_run_mode(self) -> None:
        original = (self.root / "data" / "talks.bib").read_text(encoding="utf-8")
        completed = self.run_cli("normalize", "talks", "--dry-run")
        current = (self.root / "data" / "talks.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("set note", completed.stdout)
        self.assertEqual(original, current)

    def test_normalize_apply_mode_on_safe_example(self) -> None:
        completed = self.run_cli("normalize", "talks", "--apply")
        current = (self.root / "data" / "talks.bib").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("remove venue", completed.stdout)
        self.assertNotIn("venue =", current)

    def test_render_compatibility_after_edit_import_and_normalize(self) -> None:
        self.run_cli("edit", "talks", "barbosa_agu_2026", "--set", "note=Normalized Talk")
        self.run_cli(
            "import-bibtex",
            "publications",
            "--string",
            "@article{renderpaper, title={Renderable Imported Paper}, author={Doe, John}, year={2025}, doi={10.1000/renderable.doi}}",
        )
        self.run_cli("normalize", "talks", "--apply")
        render_completed = self.run_cli("render", "--output", "milestone3_cv")
        tex_output = (self.root / "output" / "milestone3_cv.tex").read_text(encoding="utf-8")

        self.assertEqual(render_completed.returncode, 0)
        self.assertIn("Renderable Imported Paper", tex_output)
        self.assertIn("Normalized Talk", tex_output)


if __name__ == "__main__":
    unittest.main()
