import tempfile
import unittest
from pathlib import Path

from src.bibtex_ops import BibTeXManager
from src.check_ops import ProjectChecker
from src.render_ops import CVRenderer


TEST_CONFIG = """{
  "categories": {
    "publications": "data/publications.bib",
    "talks": "data/talks.bib",
    "students": "data/students.bib"
  },
  "required_fields": {
    "publications": ["entry_type", "cite_key", "title", "author", "year"],
    "talks": ["entry_type", "cite_key", "title", "author", "year"],
    "students": ["entry_type", "cite_key", "title", "year"]
  },
  "template_name": "basic_cv",
  "latex_engine": "xelatex",
  "output_dir": "output",
  "author_name": "Sample Academic"
}"""

BASIC_TEMPLATE = r"""\documentclass{article}
\begin{document}
\CVList[collection=publications, sort=year_desc, list=enumerate, format="<<author>>, <<year>>: <<title>>, <<journal>>, <<doi>>"]
\CVList[collection=students, sort=lastname, list=etaremune, format="<<title>>, <<year>>, <<school>>"]
\end{document}
"""

MALFORMED_TEMPLATE = r"""\documentclass{article}
\begin{document}
\CVList[collection=publications, sort=year_desc, list=enumerate, format="<<title>>"
\end{document}
"""

INVALID_OPTION_TEMPLATE = r"""\documentclass{article}
\begin{document}
\CVList[collection=publications, sort=nope, list=enumerate, format="<<title>>"]
\end{document}
"""

UNKNOWN_COLLECTION_TEMPLATE = r"""\documentclass{article}
\begin{document}
\CVList[collection=missing_collection, sort=year_desc, list=enumerate, format="<<title>>"]
\end{document}
"""

PUBLICATIONS_BIB = """@article{paper1,
  title = {Shared Title},
  author = {Jane Doe},
  year = {2024},
}

@article{paper2,
  title = {Shared Title},
  author = {John Doe},
  year = {2023},
  doi = {10.1000/example},
  journal = {Example Journal},
}

@article{paper3,
  title = {Different Title},
  author = {Alex Doe},
  year = {2022},
  doi = {https://doi.org/10.1000/example},
  journal = {Example Journal},
}
"""

TALKS_BIB = """@misc{talk1,
  title = {Talk Title},
  author = {Speaker Person},
  date = {2025/05/12},
}
"""

STUDENTS_BIB = """@phdthesis{student1,
  title = {Thesis Title},
  year = {2026},
  school = {Example University},
}
"""


class CheckOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "data").mkdir()
        (self.root / "templates").mkdir()
        (self.root / "output").mkdir()
        (self.root / "config.json").write_text(TEST_CONFIG, encoding="utf-8")
        (self.root / "templates" / "basic_cv.tex").write_text(BASIC_TEMPLATE, encoding="utf-8")
        (self.root / "templates" / "broken.tex").write_text(MALFORMED_TEMPLATE, encoding="utf-8")
        (self.root / "templates" / "invalid_option.tex").write_text(INVALID_OPTION_TEMPLATE, encoding="utf-8")
        (self.root / "templates" / "unknown_collection.tex").write_text(UNKNOWN_COLLECTION_TEMPLATE, encoding="utf-8")
        (self.root / "data" / "publications.bib").write_text(PUBLICATIONS_BIB, encoding="utf-8")
        (self.root / "data" / "talks.bib").write_text(TALKS_BIB, encoding="utf-8")
        (self.root / "data" / "students.bib").write_text(STUDENTS_BIB, encoding="utf-8")

        self.manager = BibTeXManager(self.root)
        self.renderer = CVRenderer(self.root, self.manager)
        self.checker = ProjectChecker(self.root, self.manager, self.renderer)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_check_preserves_existing_data_validity_logic(self) -> None:
        report = self.checker.run()
        combined = "\n".join(report.data_validity_errors)

        self.assertIn("malformed date '2025/05/12'", combined)
        self.assertIn("Duplicate DOI '10.1000/example'", combined)

    def test_duplicate_title_is_warning_not_error(self) -> None:
        report = self.checker.run()
        self.assertTrue(any("Duplicate title 'Shared Title'" in item for item in report.data_quality_warnings))
        self.assertFalse(any("Duplicate title 'Shared Title'" in item for item in report.data_validity_errors))

    def test_template_coverage_warnings_are_separate_from_data_errors(self) -> None:
        report = self.checker.run()
        template_text = "\n".join(report.template_coverage_warnings)
        error_text = "\n".join(report.data_validity_errors)

        self.assertIn("missing format field(s): journal, doi", template_text)
        self.assertNotIn("missing format field(s): journal", error_text)
        self.assertNotIn("missing format field(s): doi", error_text)

    def test_optional_template_field_does_not_become_required_data_error(self) -> None:
        report = self.checker.run()
        error_text = "\n".join(report.data_validity_errors)
        template_text = "\n".join(report.template_coverage_warnings)

        self.assertNotIn("missing required field 'doi'", error_text)
        self.assertIn("missing format field(s): journal, doi", template_text)

    def test_template_syntax_and_option_problems_are_reported(self) -> None:
        report = self.checker.run()
        config_text = "\n".join(report.configuration_issues)

        self.assertIn("Template 'broken.tex':", config_text)
        self.assertIn("Template 'invalid_option.tex':", config_text)
        self.assertIn("Template 'unknown_collection.tex':", config_text)

    def test_sort_requirements_missing_field_are_template_warning(self) -> None:
        report = self.checker.run()
        template_text = "\n".join(report.template_coverage_warnings)
        error_text = "\n".join(report.data_validity_errors)

        self.assertIn("sorts by 'lastname', but entry 'student1' is missing 'author'", template_text)
        self.assertNotIn("student1", error_text)


if __name__ == "__main__":
    unittest.main()
