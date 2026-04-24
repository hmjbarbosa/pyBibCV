from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .bibtex_ops import BibTeXManager, NormalizationChange, ParsedEntry
from .import_ops import ImportManager
from .render_ops import CVRenderer, RenderResult


class GUIController:
    """Thin application service layer shared by the Tkinter UI and tests."""

    def __init__(
        self,
        manager: BibTeXManager,
        importer: ImportManager,
        renderer: CVRenderer,
    ):
        self.manager = manager
        self.importer = importer
        self.renderer = renderer

    @classmethod
    def from_root_dir(cls, root_dir: Path) -> "GUIController":
        manager = BibTeXManager(root_dir)
        manager.ensure_storage()
        importer = ImportManager(manager)
        renderer = CVRenderer(root_dir, manager)
        return cls(manager, importer, renderer)

    def collections(self) -> List[str]:
        return self.manager.categories()

    def required_fields(self, category: str) -> List[str]:
        return self.manager.required_fields_for_category(category)

    def known_entry_types(self, category: str) -> List[str]:
        return self.manager.known_entry_types(category)

    def list_entries(self, category: str) -> List[ParsedEntry]:
        return self.manager.list_entries(category)

    def get_entry(self, category: str, cite_key: str) -> ParsedEntry:
        return self.manager.get_entry(category, cite_key)

    def add_entry(self, category: str, entry: Dict[str, str]) -> ParsedEntry:
        self.manager.add_entry(category, entry)
        return self.manager.get_entry(category, entry["cite_key"])

    def edit_entry(
        self,
        category: str,
        cite_key: str,
        set_fields: Dict[str, str],
        remove_fields: List[str],
    ) -> ParsedEntry:
        return self.manager.update_entry(category, cite_key, set_fields, remove_fields)

    def import_doi(self, category: str, doi: str, cite_key: Optional[str] = None) -> ParsedEntry:
        return self.importer.import_doi(category, doi, requested_key=cite_key)

    def import_bibtex_file(self, category: str, file_path: str) -> List[ParsedEntry]:
        return self.importer.import_bibtex_file(category, file_path)

    def import_bibtex_string(self, category: str, bibtex_string: str) -> List[ParsedEntry]:
        return self.importer.import_bibtex_string(category, bibtex_string)

    def validate(self, category: Optional[str] = None) -> List[str]:
        return self.manager.lint_category(category) if category else self.manager.lint_all()

    def normalize(self, category: str, apply_changes: bool) -> Tuple[List[NormalizationChange], List[str]]:
        return self.manager.normalize_collection(category, dry_run=not apply_changes)

    def render(
        self,
        output_name: str = "cv",
        compile_pdf: bool = False,
        template_name: Optional[str] = None,
    ) -> RenderResult:
        return self.renderer.render(
            template_name=template_name,
            output_name=output_name,
            compile_pdf=compile_pdf,
        )
