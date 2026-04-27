import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


TEST_CONFIG = """{
  "categories": {
    "publications": "data/publications.bib",
    "talks": "data/talks.bib"
  },
  "required_fields": {
    "publications": ["entry_type", "cite_key", "title", "author", "year"],
    "talks": ["entry_type", "cite_key", "title", "author", "year"]
  },
  "template_name": "basic_cv",
  "latex_engine": "xelatex",
  "output_dir": "output",
  "author_name": "Sample Academic"
}"""

TEST_TEMPLATE = r"""\documentclass{article}
\begin{document}
\section*{Publications}
\CVList[collection=publications, sort=year_desc, list=enumerate, format="<<author>>, <<year>>: <<title>>"]
\section*{Talks}
\CVList[collection=talks, sort=year_desc, list=itemize, format="<<title>>, <<year>>"]
\end{document}
"""

PUBLICATIONS_BIB = """@article{doe2024,
  title = {Recent Publication},
  author = {Jane Doe},
  year = {2024},
  journal = {Example Journal},
}
"""

TALKS_BIB = """@misc{talk2025,
  title = {Workflow Talk},
  author = {Sam Speaker},
  year = {2025},
  note = {Research workflow seminar},
}
"""


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "src").mkdir()
        (self.root / "data").mkdir()
        (self.root / "templates").mkdir()
        (self.root / "output").mkdir()

        project_root = Path(__file__).resolve().parents[1]
        shutil.copy2(project_root / "cli.py", self.root / "cli.py")
        shutil.copy2(project_root / "src" / "__init__.py", self.root / "src" / "__init__.py")
        shutil.copy2(project_root / "src" / "bibtex_ops.py", self.root / "src" / "bibtex_ops.py")
        shutil.copy2(project_root / "src" / "import_ops.py", self.root / "src" / "import_ops.py")
        shutil.copy2(project_root / "src" / "render_ops.py", self.root / "src" / "render_ops.py")

        (self.root / "config.json").write_text(TEST_CONFIG, encoding="utf-8")
        (self.root / "templates" / "basic_cv.tex").write_text(TEST_TEMPLATE, encoding="utf-8")
        (self.root / "data" / "publications.bib").write_text(PUBLICATIONS_BIB, encoding="utf-8")
        (self.root / "data" / "talks.bib").write_text(TALKS_BIB, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", "cli.py", *args],
            cwd=self.root,
            input=user_input,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_add_creates_valid_entry_in_correct_file(self) -> None:
        completed = self.run_cli(
            "add",
            "publications",
            user_input="article\nnew2026\nNew Entry\nTaylor Writer\n2026\njournal\nTesting Journal\n\n",
        )

        self.assertEqual(completed.returncode, 0)
        updated = (self.root / "data" / "publications.bib").read_text(encoding="utf-8")
        self.assertIn("@article{new2026,", updated)
        self.assertIn("journal = {Testing Journal}", updated)
        self.assertIn("existing: article", completed.stdout)

    def test_list_displays_entries_from_correct_collection(self) -> None:
        completed = self.run_cli("list", "talks")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("talk2025", completed.stdout)
        self.assertIn("Workflow Talk", completed.stdout)

    def test_lint_runs_and_reports_results(self) -> None:
        completed = self.run_cli("lint")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("No lint issues found in all categories.", completed.stdout)

    def test_interactive_mode_starts_and_help_and_quit_work(self) -> None:
        completed = self.run_cli(user_input="help\nquit\n")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("pyBibCV>", completed.stdout)
        self.assertIn("Commands:", completed.stdout)
        self.assertIn("add <category>", completed.stdout)

    def test_exit_works_in_interactive_mode(self) -> None:
        completed = self.run_cli(user_input="exit\n")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("pyBibCV>", completed.stdout)

    def test_invalid_collection_names_produce_clear_errors(self) -> None:
        completed = self.run_cli("list", "unknown")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Unknown category 'unknown'", completed.stdout)

    def test_edit_without_flags_prompts_interactively(self) -> None:
        completed = self.run_cli(
            "edit",
            "talks",
            "talk2025",
            user_input="\n\nUpdated Talk Title\n\n\n\n\n",
        )

        updated = (self.root / "data" / "talks.bib").read_text(encoding="utf-8")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("Updated Talk Title", updated)
        self.assertIn("existing: misc", completed.stdout)


if __name__ == "__main__":
    unittest.main()
