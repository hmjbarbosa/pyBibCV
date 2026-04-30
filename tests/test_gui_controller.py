import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

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
        self.assertFalse(hasattr(PyBibCVApp, "edit_entry"))

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

    def test_replace_entry_from_raw_through_gui_connected_logic(self) -> None:
        updated = self.controller.replace_entry_from_raw(
            "talks",
            "talk2026",
            """@misc{talk2026,
  title = {Updated Inline Talk},
  author = {Taylor Speaker},
  year = {2026},
  note = {Updated in details panel},
}""",
        )

        self.assertEqual(updated["fields"]["title"], "Updated Inline Talk")
        self.assertEqual(updated["fields"]["note"], "Updated in details panel")

    def test_inline_save_persists_changes_to_disk(self) -> None:
        class FakeText:
            def __init__(self, contents: str) -> None:
                self.contents = contents
                self.modified = False

            def get(self, start: str, end: str) -> str:
                return self.contents

            def config(self, **kwargs: str) -> None:
                return None

            def delete(self, start: str, end: str) -> None:
                self.contents = ""

            def insert(self, index: str, text: str) -> None:
                self.contents = text

            def edit_modified(self, value: Optional[bool] = None) -> bool:
                if value is None:
                    return self.modified
                self.modified = value
                return self.modified

        class FakeListbox:
            def __init__(self) -> None:
                self.items = []
                self.selected_index = None

            def delete(self, start: int, end: str) -> None:
                self.items = []

            def insert(self, index: str, text: str) -> None:
                self.items.append(text)

            def selection_clear(self, start: int, end: str) -> None:
                self.selected_index = None

            def selection_set(self, index: int) -> None:
                self.selected_index = index

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.controller = self.controller
        app.current_category = "talks"
        app.current_entry_key = "talk2026"
        app.current_entries = self.controller.list_entries("talks")
        app.collection_list = FakeListbox()
        app.entry_list = FakeListbox()
        app.save_detail_button = mock.Mock()
        app.detail_text = FakeText(
            """@misc{talk2026,
  title = {Persisted Inline Talk},
  author = {Taylor Speaker},
  year = {2026},
  note = {Saved to disk},
}"""
        )
        app.detail_dirty = True
        app._loading_detail = False
        app._suppress_selection_events = False
        app.write_output = mock.Mock()
        app.show_error = mock.Mock()

        app.save_detail_changes()

        reloaded = self.controller.get_entry("talks", "talk2026")
        self.assertEqual(reloaded["fields"]["title"], "Persisted Inline Talk")
        self.assertEqual(reloaded["fields"]["note"], "Saved to disk")
        self.assertIn("Persisted Inline Talk", app.detail_text.contents)
        app.show_error.assert_not_called()

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

    def test_show_entry_detail_loads_text_into_editor(self) -> None:
        class FakeText:
            def __init__(self) -> None:
                self.contents = ""
                self.modified = False

            def config(self, **kwargs: str) -> None:
                return None

            def insert(self, index: str, text: str) -> None:
                self.contents += text

            def delete(self, start: str, end: str) -> None:
                self.contents = ""

            def edit_modified(self, value: Optional[bool] = None) -> bool:
                if value is None:
                    return self.modified
                self.modified = value
                return self.modified

        class FakeButton:
            def __init__(self) -> None:
                self.state = None

            def config(self, **kwargs: str) -> None:
                self.state = kwargs.get("state")

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.detail_text = FakeText()
        app.save_detail_button = FakeButton()
        app._loading_detail = False
        app.detail_dirty = False

        entry = self.controller.get_entry("publications", "smith2024paper")
        app.show_entry_detail(entry)

        self.assertIn("@article{smith2024paper,", app.detail_text.contents)
        self.assertEqual(app.save_detail_button.state, "normal")
        self.assertFalse(app.detail_dirty)

    def test_save_detail_changes_saves_valid_inline_edit(self) -> None:
        class FakeText:
            def __init__(self, contents: str) -> None:
                self.contents = contents

            def get(self, start: str, end: str) -> str:
                return self.contents

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "talks"
        app.current_entry_key = "talk2026"
        app.detail_text = FakeText(
            """@misc{talk2026,
  title = {Saved Inline Talk},
  author = {Taylor Speaker},
  year = {2026},
}"""
        )
        app.controller = mock.Mock()
        app.controller.replace_entry_from_raw.return_value = {
            "entry_type": "misc",
            "cite_key": "talk2026",
            "fields": {
                "entry_type": "misc",
                "cite_key": "talk2026",
                "title": "Saved Inline Talk",
                "author": "Taylor Speaker",
                "year": "2026",
            },
        }
        app.refresh_after_change = mock.Mock()
        app.write_output = mock.Mock()
        app.show_error = mock.Mock()

        app.save_detail_changes()

        app.controller.replace_entry_from_raw.assert_called_once()
        app.refresh_after_change.assert_called_once_with("talks", "talk2026")
        app.write_output.assert_called_once()
        app.show_error.assert_not_called()

    def test_save_detail_changes_fails_cleanly_on_invalid_bibtex(self) -> None:
        class FakeText:
            def get(self, start: str, end: str) -> str:
                return "@misc{broken"

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "talks"
        app.current_entry_key = "talk2026"
        app.detail_text = FakeText()
        app.controller = mock.Mock()
        app.controller.replace_entry_from_raw.side_effect = ValueError("invalid BibTeX header")
        app.refresh_after_change = mock.Mock()
        app.write_output = mock.Mock()
        app.show_error = mock.Mock()

        app.save_detail_changes()

        app.show_error.assert_called_once_with("invalid BibTeX header")
        app.refresh_after_change.assert_not_called()
        app.write_output.assert_not_called()

    def test_unsaved_changes_warn_before_switching_entries(self) -> None:
        class FakeListbox:
            def curselection(self) -> tuple[int]:
                return (1,)

            def selection_clear(self, start: int, end: str) -> None:
                return None

            def selection_set(self, index: int) -> None:
                return None

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "talks"
        app.current_entry_key = "talk2026"
        app.current_entries = [
            {"entry_type": "misc", "cite_key": "talk2026", "fields": {"title": "A"}},
            {"entry_type": "misc", "cite_key": "talk2027", "fields": {"title": "B"}},
        ]
        app.entry_list = FakeListbox()
        app.detail_text = mock.Mock()
        app.detail_text.get.return_value = "edited raw bibtex"
        app.save_detail_button = mock.Mock()
        app.detail_dirty = True
        app._suppress_selection_events = False
        app.clear_detail = mock.Mock()
        app.show_entry_detail = mock.Mock()
        app.restore_entry_selection = mock.Mock()
        app.confirm_discard_unsaved = mock.Mock(return_value=False)

        app.on_entry_selected()

        app.restore_entry_selection.assert_called_once()
        app.show_entry_detail.assert_not_called()
        self.assertEqual(app.current_entry_key, "talk2026")

    def test_unsaved_changes_no_restores_dirty_editor_text(self) -> None:
        class FakeListbox:
            def curselection(self) -> tuple[int]:
                return (1,)

            def selection_clear(self, start: int, end: str) -> None:
                return None

            def selection_set(self, index: int) -> None:
                return None

        class FakeText:
            def __init__(self) -> None:
                self.contents = "edited raw bibtex"
                self.modified = False

            def get(self, start: str, end: str) -> str:
                return self.contents

            def config(self, **kwargs: str) -> None:
                return None

            def delete(self, start: str, end: str) -> None:
                self.contents = ""

            def insert(self, index: str, text: str) -> None:
                self.contents = text

            def edit_modified(self, value: Optional[bool] = None) -> bool:
                if value is None:
                    return self.modified
                self.modified = value
                return self.modified

        class FakeButton:
            def __init__(self) -> None:
                self.state = None

            def config(self, **kwargs: str) -> None:
                self.state = kwargs.get("state")

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "talks"
        app.current_entry_key = "talk2026"
        app.current_entries = [
            {"entry_type": "misc", "cite_key": "talk2026", "fields": {"title": "A"}},
            {"entry_type": "misc", "cite_key": "talk2027", "fields": {"title": "B"}},
        ]
        app.entry_list = FakeListbox()
        app.detail_text = FakeText()
        app.save_detail_button = FakeButton()
        app.detail_dirty = True
        app._loading_detail = False
        app._suppress_selection_events = False
        app.show_entry_detail = mock.Mock()
        app.restore_entry_selection = mock.Mock()
        app.confirm_discard_unsaved = mock.Mock(return_value=False)

        app.on_entry_selected()

        self.assertEqual(app.detail_text.contents, "edited raw bibtex")
        self.assertTrue(app.detail_dirty)
        self.assertEqual(app.save_detail_button.state, "normal")
        app.show_entry_detail.assert_not_called()

    def test_clicking_same_entry_does_not_discard_unsaved_changes(self) -> None:
        class FakeListbox:
            def curselection(self) -> tuple[int]:
                return (0,)

        class FakeText:
            def __init__(self) -> None:
                self.contents = "edited raw bibtex"

            def get(self, start: str, end: str) -> str:
                return self.contents

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "talks"
        app.current_entry_key = "talk2026"
        app.current_entries = [
            {"entry_type": "misc", "cite_key": "talk2026", "fields": {"title": "A"}},
            {"entry_type": "misc", "cite_key": "talk2027", "fields": {"title": "B"}},
        ]
        app.entry_list = FakeListbox()
        app.detail_text = FakeText()
        app.detail_dirty = True
        app._suppress_selection_events = False
        app.show_entry_detail = mock.Mock()
        app.confirm_discard_unsaved = mock.Mock()

        app.on_entry_selected()

        self.assertEqual(app.detail_text.contents, "edited raw bibtex")
        app.show_entry_detail.assert_not_called()
        app.confirm_discard_unsaved.assert_not_called()

    def test_unsaved_changes_yes_switches_to_new_entry(self) -> None:
        class FakeListbox:
            def __init__(self) -> None:
                self.selected_index = 1

            def curselection(self) -> tuple[int]:
                return (self.selected_index,)

            def selection_clear(self, start: int, end: str) -> None:
                return None

            def selection_set(self, index: int) -> None:
                self.selected_index = index

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "talks"
        app.current_entry_key = "talk2026"
        app.current_entries = [
            {"entry_type": "misc", "cite_key": "talk2026", "fields": {"title": "A"}},
            {"entry_type": "misc", "cite_key": "talk2027", "fields": {"title": "B"}},
        ]
        app.entry_list = FakeListbox()
        app.detail_text = mock.Mock()
        app.detail_text.get.return_value = "edited raw bibtex"
        app.detail_dirty = True
        app._suppress_selection_events = False
        app.show_entry_detail = mock.Mock()
        app.confirm_discard_unsaved = mock.Mock(return_value=True)

        app.on_entry_selected()

        self.assertEqual(app.current_entry_key, "talk2027")
        app.show_entry_detail.assert_called_once_with(app.current_entries[1])

    def test_clicking_same_collection_does_not_discard_unsaved_changes(self) -> None:
        class FakeCollectionListbox:
            def curselection(self) -> tuple[int]:
                return (0,)

            def get(self, index: int) -> str:
                return "publications"

        class FakeText:
            def __init__(self) -> None:
                self.contents = "edited raw bibtex"

            def get(self, start: str, end: str) -> str:
                return self.contents

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "publications"
        app.current_entry_key = "smith2024paper"
        app.collection_list = FakeCollectionListbox()
        app.detail_text = FakeText()
        app.detail_dirty = True
        app._suppress_selection_events = False
        app._pending_collection_index = None
        app._ignore_collection_events_until_idle = False
        app.confirm_discard_unsaved = mock.Mock()
        app.schedule_collection_selection = mock.Mock()

        app.on_collection_selected()

        self.assertEqual(app.detail_text.contents, "edited raw bibtex")
        app.confirm_discard_unsaved.assert_not_called()
        app.schedule_collection_selection.assert_not_called()

    def test_unsaved_collection_switch_no_restores_current_collection(self) -> None:
        class FakeCollectionListbox:
            def curselection(self) -> tuple[int]:
                return (1,)

            def get(self, index: int) -> str:
                return ["publications", "talks"][index]

            def selection_clear(self, start: int, end: str) -> None:
                return None

            def selection_set(self, index: int) -> None:
                return None

        class FakeText:
            def __init__(self) -> None:
                self.contents = "edited raw bibtex"
                self.modified = False

            def get(self, start: str, end: str) -> str:
                return self.contents

            def config(self, **kwargs: str) -> None:
                return None

            def delete(self, start: str, end: str) -> None:
                self.contents = ""

            def insert(self, index: str, text: str) -> None:
                self.contents = text

            def edit_modified(self, value: Optional[bool] = None) -> bool:
                if value is None:
                    return self.modified
                self.modified = value
                return self.modified

        class FakeButton:
            def __init__(self) -> None:
                self.state = None

            def config(self, **kwargs: str) -> None:
                self.state = kwargs.get("state")

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "publications"
        app.collection_list = FakeCollectionListbox()
        app.detail_text = FakeText()
        app.save_detail_button = FakeButton()
        app.detail_dirty = True
        app._loading_detail = False
        app._suppress_selection_events = False
        app._pending_collection_index = None
        app._ignore_collection_events_until_idle = False
        app.restore_collection_selection = mock.Mock()
        app.confirm_discard_unsaved = mock.Mock(return_value=False)
        app.schedule_collection_selection = mock.Mock()
        app.root = mock.Mock()

        app.on_collection_selected()

        app.restore_collection_selection.assert_called_once()
        app.schedule_collection_selection.assert_not_called()
        self.assertEqual(app.current_category, "publications")
        self.assertEqual(app.detail_text.contents, "edited raw bibtex")

    def test_unsaved_collection_switch_yes_moves_to_clicked_collection(self) -> None:
        class FakeCollectionListbox:
            def __init__(self) -> None:
                self.selected_index = 1

            def curselection(self) -> tuple[int]:
                return (self.selected_index,)

            def get(self, index: int) -> str:
                return ["publications", "talks", "students"][index]

            def selection_clear(self, start: int, end: str) -> None:
                return None

            def selection_set(self, index: int) -> None:
                self.selected_index = index

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "publications"
        app.current_entry_key = "smith2024paper"
        app.current_entries = [{"entry_type": "article", "cite_key": "smith2024paper", "fields": {"title": "A"}}]
        app.collection_list = FakeCollectionListbox()
        app.entry_list = mock.Mock()
        app.detail_text = mock.Mock()
        app.detail_text.get.return_value = "edited raw bibtex"
        app.detail_dirty = True
        app._suppress_selection_events = False
        app._pending_collection_index = None
        app._ignore_collection_events_until_idle = False
        app.confirm_discard_unsaved = mock.Mock(return_value=True)
        app.controller = mock.Mock()
        app.controller.collections.return_value = ["publications", "talks", "students"]
        app.controller.list_entries.return_value = []
        app.clear_detail = mock.Mock()

        app.on_collection_selected()

        self.assertEqual(app.current_category, "talks")
        app.controller.list_entries.assert_called_once_with("talks")
        app.clear_detail.assert_called_once()

    def test_pending_collection_switch_ignores_repeat_selection_event(self) -> None:
        class FakeCollectionListbox:
            def curselection(self) -> tuple[int]:
                return (1,)

            def get(self, index: int) -> str:
                return ["publications", "talks", "students"][index]

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "publications"
        app.collection_list = FakeCollectionListbox()
        app.detail_text = mock.Mock()
        app.detail_text.get.return_value = "edited raw bibtex"
        app.detail_dirty = True
        app._suppress_selection_events = False
        app._pending_collection_index = 1
        app.confirm_discard_unsaved = mock.Mock()
        app.schedule_collection_selection = mock.Mock()

        app.on_collection_selected()

        app.confirm_discard_unsaved.assert_not_called()
        app.schedule_collection_selection.assert_not_called()

    def test_rejected_collection_switch_ignores_immediate_repeat_event(self) -> None:
        class FakeCollectionListbox:
            def curselection(self) -> tuple[int]:
                return (1,)

            def get(self, index: int) -> str:
                return ["publications", "talks", "students"][index]

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "publications"
        app.collection_list = FakeCollectionListbox()
        app.detail_text = mock.Mock()
        app.detail_text.get.return_value = "edited raw bibtex"
        app.detail_dirty = True
        app._suppress_selection_events = False
        app._pending_collection_index = None
        app._ignore_collection_events_until_idle = True
        app.confirm_discard_unsaved = mock.Mock()
        app.restore_collection_selection = mock.Mock()
        app.schedule_collection_selection = mock.Mock()

        app.on_collection_selected()

        app.confirm_discard_unsaved.assert_not_called()
        app.restore_collection_selection.assert_called_once()
        app.schedule_collection_selection.assert_not_called()

    def test_rejected_collection_switch_sets_idle_ignore_guard(self) -> None:
        class FakeCollectionListbox:
            def curselection(self) -> tuple[int]:
                return (1,)

            def get(self, index: int) -> str:
                return ["publications", "talks", "students"][index]

        class FakeText:
            def get(self, start: str, end: str) -> str:
                return "edited raw bibtex"

        app = PyBibCVApp.__new__(PyBibCVApp)
        app.current_category = "publications"
        app.collection_list = FakeCollectionListbox()
        app.detail_text = FakeText()
        app.detail_dirty = True
        app._suppress_selection_events = False
        app._pending_collection_index = None
        app._ignore_collection_events_until_idle = False
        app.restore_collection_selection = mock.Mock()
        app.restore_dirty_detail_snapshot = mock.Mock()
        app.confirm_discard_unsaved = mock.Mock(return_value=False)
        app.root = mock.Mock()

        app.on_collection_selected()

        self.assertTrue(app._ignore_collection_events_until_idle)
        app.root.after_idle.assert_called_once()

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
