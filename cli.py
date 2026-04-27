import argparse
import shlex
from pathlib import Path
from typing import Dict, List, Optional

try:
    import readline
except ImportError:  # pragma: no cover - depends on platform Python build
    readline = None  # type: ignore[assignment]

from src.bibtex_ops import BibTeXManager, NormalizationChange, ParsedEntry
from src.import_ops import DOIImportError, ImportManager
from src.render_ops import CVRenderer, RenderResult


class CVCLI:
    def __init__(self, manager: BibTeXManager, renderer: CVRenderer, importer: ImportManager):
        self.manager = manager
        self.renderer = renderer
        self.importer = importer

    def run(self, command: str, category: Optional[str] = None, options: Optional[List[str]] = None) -> int:
        option_list = options or []
        if command == "add":
            return self.handle_add(category)
        if command == "list":
            return self.handle_list(category)
        if command == "lint":
            return self.handle_lint(category)
        if command == "render":
            return self.handle_render(category, option_list)
        if command == "show":
            return self.handle_show(category, option_list)
        if command == "edit":
            return self.handle_edit(category, option_list)
        if command == "import-doi":
            return self.handle_import_doi(category, option_list)
        if command == "import-bibtex":
            return self.handle_import_bibtex(category, option_list)
        if command == "normalize":
            return self.handle_normalize(category, option_list)
        if command in {"help", "?"}:
            self.print_help()
            return 0
        if command in {"exit", "quit"}:
            return 1

        print(f"Unknown command '{command}'.")
        self.print_help()
        return 0

    def handle_add(self, category: Optional[str]) -> int:
        if not category:
            print(f"Please provide a category. Available: {', '.join(self.manager.categories())}")
            return 0

        try:
            self.manager.category_path(category)
        except ValueError as exc:
            print(exc)
            return 0

        print(f"Adding a new entry to '{category}'. Leave optional fields blank.")
        entry_type_prompt = self.build_entry_type_prompt(category)
        entry = {
            "entry_type": input(entry_type_prompt).strip(),
            "cite_key": input("Citation key: ").strip(),
        }
        for field_name in self.required_nonstructural_fields(category):
            entry[field_name] = input(f"{self.label_for_field(field_name)}: ").strip()

        while True:
            field_name = input("Extra field name (press Enter to finish): ").strip()
            if not field_name:
                break
            entry[field_name] = input(f"Value for {field_name}: ").strip()

        try:
            self.manager.add_entry(category, entry)
        except ValueError as exc:
            print(exc)
            return 0
        print(f"Saved entry '{entry['cite_key']}' to {self.manager.category_path(category)}")
        return 0

    def handle_list(self, category: Optional[str]) -> int:
        if not category:
            print(f"Please provide a category. Available: {', '.join(self.manager.categories())}")
            return 0

        try:
            entries = self.manager.list_entries(category)
        except ValueError as exc:
            print(exc)
            return 0

        if not entries:
            print(f"No entries found in '{category}'.")
            return 0

        for index, entry in enumerate(entries, start=1):
            fields = entry["fields"]
            print(f"{index}. {entry['cite_key']} [{entry['entry_type']}]")
            print(f"   Title: {fields.get('title', '(missing)')}")
            print(f"   Author: {fields.get('author', '(missing)')}")
            print(f"   Year: {fields.get('year', '(missing)')}")
        return 0

    def handle_lint(self, category: Optional[str]) -> int:
        try:
            issues = self.manager.lint_category(category) if category else self.manager.lint_all()
        except ValueError as exc:
            print(exc)
            return 0

        if not issues:
            target = category if category else "all categories"
            print(f"No lint issues found in {target}.")
            return 0

        print("Lint issues:")
        for issue in issues:
            print(f"- {issue}")
        return 0

    def handle_render(self, category: Optional[str], options: List[str]) -> int:
        parser = build_render_parser()

        try:
            args = parser.parse_args(([category] if category else []) + options)
        except SystemExit:
            return 0

        result = self.renderer.render(
            template_name=args.template,
            output_name=args.output,
            min_year=args.min_year,
            keyword=args.keyword,
            compile_pdf=args.compile_pdf,
        )
        self.print_render_result(result)
        return 0

    def handle_show(self, category: Optional[str], options: List[str]) -> int:
        parser = build_show_parser()
        try:
            args = parser.parse_args(([category] if category else []) + options)
            entry = self.manager.get_entry(args.category, args.cite_key)
        except (SystemExit, ValueError) as exc:
            if isinstance(exc, ValueError):
                print(exc)
            return 0

        self.print_entry(entry)
        return 0

    def handle_edit(self, category: Optional[str], options: List[str]) -> int:
        parser = build_edit_parser()
        try:
            args = parser.parse_args(([category] if category else []) + options)
        except SystemExit:
            return 0

        set_fields: Dict[str, str] = {}
        for item in args.set_items or []:
            if "=" not in item:
                print(f"Invalid --set value '{item}'. Use field=value.")
                return 0
            field, value = item.split("=", 1)
            set_fields[field] = value

        if not set_fields and not (args.remove_items or []):
            return self.handle_edit_interactive(args.category, args.cite_key)

        try:
            updated_entry = self.manager.update_entry(args.category, args.cite_key, set_fields, args.remove_items or [])
        except ValueError as exc:
            print(exc)
            return 0

        print(f"Updated entry '{updated_entry['cite_key']}' in '{args.category}'.")
        self.print_entry(updated_entry)
        return 0

    def handle_import_doi(self, category: Optional[str], options: List[str]) -> int:
        parser = build_import_doi_parser()
        try:
            args = parser.parse_args(([category] if category else []) + options)
            imported_entry = self.importer.import_doi(args.category, args.doi, requested_key=args.key)
        except SystemExit:
            return 0
        except (DOIImportError, ValueError) as exc:
            print(exc)
            return 0

        print(f"Imported DOI '{args.doi}' into '{args.category}'.")
        self.print_entry(imported_entry)
        return 0

    def handle_import_bibtex(self, category: Optional[str], options: List[str]) -> int:
        parser = build_import_bibtex_parser()
        try:
            args = parser.parse_args(([category] if category else []) + options)
            if args.file_path:
                imported_entries = self.importer.import_bibtex_file(args.category, args.file_path)
            else:
                imported_entries = self.importer.import_bibtex_string(args.category, args.string_value)
        except SystemExit:
            return 0
        except (DOIImportError, OSError, ValueError) as exc:
            print(exc)
            return 0

        print(f"Imported {len(imported_entries)} BibTeX entr{'y' if len(imported_entries) == 1 else 'ies'} into '{args.category}'.")
        for entry in imported_entries:
            self.print_entry(entry)
        return 0

    def handle_normalize(self, category: Optional[str], options: List[str]) -> int:
        parser = build_normalize_parser()
        try:
            args = parser.parse_args(([category] if category else []) + options)
        except SystemExit:
            return 0

        try:
            changes, warnings = self.manager.normalize_collection(args.category, dry_run=not args.apply)
        except ValueError as exc:
            print(exc)
            return 0

        if not changes and not warnings:
            print(f"No normalization changes needed in '{args.category}'.")
            return 0

        mode = "Applying" if args.apply else "Dry run for"
        print(f"{mode} normalization in '{args.category}':")
        for change in changes:
            self.print_normalization_change(change)
        for warning in warnings:
            print(f"Warning: {warning}")
        return 0

    def handle_edit_interactive(self, category: str, cite_key: str) -> int:
        try:
            entry = self.manager.get_entry(category, cite_key)
        except ValueError as exc:
            print(exc)
            return 0

        print(f"Editing entry '{cite_key}' in '{category}'. Press Enter to keep the current value.")
        updated_fields: Dict[str, str] = {}
        prompted_fields: List[str] = []

        entry_type_prompt = self.build_entry_type_prompt(category, current_value=entry["entry_type"])
        new_entry_type = input(entry_type_prompt).strip()
        if new_entry_type:
            updated_fields["entry_type"] = new_entry_type
        prompted_fields.append("entry_type")

        new_cite_key = input(f"Citation key ({entry['cite_key']}): ").strip()
        if new_cite_key:
            updated_fields["cite_key"] = new_cite_key
        prompted_fields.append("cite_key")

        fields_to_prompt = self.edit_prompt_fields(category, entry)
        for field_name in fields_to_prompt:
            current_value = entry["fields"].get(field_name, "")
            prompt = f"{self.label_for_field(field_name)}"
            if current_value:
                prompt += f" ({current_value})"
            prompt += ": "
            new_value = input(prompt).strip()
            if new_value:
                updated_fields[field_name] = new_value
            prompted_fields.append(field_name)

        while True:
            field_name = input("Extra field name to edit (press Enter to finish): ").strip()
            if not field_name:
                break
            current_value = entry["fields"].get(field_name, "")
            prompt = f"Value for {field_name}"
            if current_value:
                prompt += f" ({current_value})"
            prompt += ": "
            new_value = input(prompt).strip()
            if new_value:
                updated_fields[field_name] = new_value

        try:
            updated_entry = self.manager.update_entry(category, cite_key, updated_fields, [])
        except ValueError as exc:
            print(exc)
            return 0

        print(f"Updated entry '{updated_entry['cite_key']}' in '{category}'.")
        self.print_entry(updated_entry)
        return 0

    def build_entry_type_prompt(self, category: str, current_value: Optional[str] = None) -> str:
        known_types = self.manager.known_entry_types(category)
        if known_types:
            joined = ", ".join(known_types)
            prompt = f"Entry type (existing: {joined}"
            if current_value:
                prompt += f"; current: {current_value}"
            prompt += "): "
            return prompt
        if current_value:
            return f"Entry type ({current_value}): "
        return "Entry type (e.g., article, inproceedings, misc): "

    def required_nonstructural_fields(self, category: str) -> List[str]:
        return [
            field_name
            for field_name in self.manager.required_fields_for_category(category)
            if field_name not in {"entry_type", "cite_key"}
        ]

    def edit_prompt_fields(self, category: str, entry: ParsedEntry) -> List[str]:
        ordered_fields: List[str] = []
        for field_name in self.required_nonstructural_fields(category):
            if field_name not in ordered_fields:
                ordered_fields.append(field_name)
        for field_name in entry["fields"].keys():
            if field_name in {"entry_type", "cite_key"}:
                continue
            if field_name not in ordered_fields:
                ordered_fields.append(field_name)
        return ordered_fields

    @staticmethod
    def label_for_field(field_name: str) -> str:
        return field_name.replace("_", " ").title()

    def repl(self) -> int:
        self.enable_line_editing()
        self.print_help()
        while True:
            raw = input("pyBibCV> ").strip()
            if not raw:
                continue
            self.add_history_entry(raw)
            parts = shlex.split(raw)
            command = parts[0]
            category = parts[1] if len(parts) > 1 and not parts[1].startswith("-") else None
            option_start = 2 if category else 1
            should_exit = self.run(command, category, parts[option_start:])
            if should_exit == 1:
                return 0

    @staticmethod
    def enable_line_editing() -> None:
        """Enable shell-style line editing and in-memory history when readline is available."""
        if readline is None:
            return

        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set editing-mode emacs")

    @staticmethod
    def add_history_entry(raw: str) -> None:
        if readline is None or not raw:
            return

        previous = None
        history_length = readline.get_current_history_length()
        if history_length > 0:
            previous = readline.get_history_item(history_length)
        if raw != previous:
            readline.add_history(raw)

    def print_help(self) -> None:
        print("Commands:")
        print("  add <category>             - prompt for entry fields and append a BibTeX entry")
        print("  list <category>            - display all entries in a category")
        print("  lint [category]            - validate one category or all configured BibTeX files")
        print("  render [options]           - build a LaTeX CV and optionally compile a PDF")
        print("  show <category> <key>      - display one entry")
        print("  edit <category> <key>      - modify fields on an existing entry")
        print("  import-doi <category> DOI  - import metadata from a DOI")
        print("  import-bibtex <category>   - import BibTeX from a file or string")
        print("  normalize <category>       - preview or apply conservative cleanup rules")
        print("  help                       - show this message")
        print("  exit                       - quit interactive mode")

    @staticmethod
    def print_entry(entry: ParsedEntry) -> None:
        print(BibTeXManager.format_entry(entry["fields"]))

    @staticmethod
    def print_render_result(result: RenderResult) -> None:
        print(f"Generated TeX: {result.tex_path}")
        if result.pdf_path:
            print(f"Generated PDF: {result.pdf_path}")
        if result.compilation_message:
            print(result.compilation_message)

    @staticmethod
    def print_normalization_change(change: NormalizationChange) -> None:
        if change["action"] == "remove":
            print(f"- {change['cite_key']}: remove {change['field']} (was '{change['old']}')")
        else:
            print(f"- {change['cite_key']}: set {change['field']} from '{change['old']}' to '{change['new']}'")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage CV-related BibTeX data.")
    parser.add_argument("command", nargs="?", help="Command to run")
    parser.add_argument("category", nargs="?", help="Category to target, such as publications or talks")
    return parser


def build_render_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="render", add_help=False)
    parser.add_argument("--template", help="Template name without the .tex/.json extension")
    parser.add_argument("--output", default="cv", help="Base filename for generated files")
    parser.add_argument("--min-year", type=int, help="Include only entries whose year is at least this value")
    parser.add_argument("--keyword", help="Include only entries whose fields contain this keyword")
    parser.add_argument(
        "--compile",
        dest="compile_pdf",
        action="store_true",
        help="Compile the generated TeX to PDF if a LaTeX tool is installed",
    )
    return parser


def build_show_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="show", add_help=False)
    parser.add_argument("category")
    parser.add_argument("cite_key")
    return parser


def build_edit_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edit", add_help=False)
    parser.add_argument("category")
    parser.add_argument("cite_key")
    parser.add_argument("--set", dest="set_items", action="append")
    parser.add_argument("--remove", dest="remove_items", action="append")
    return parser


def build_import_doi_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="import-doi", add_help=False)
    parser.add_argument("category")
    parser.add_argument("doi")
    parser.add_argument("--key")
    return parser


def build_import_bibtex_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="import-bibtex", add_help=False)
    parser.add_argument("category")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", dest="file_path")
    group.add_argument("--string", dest="string_value")
    return parser


def build_normalize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="normalize", add_help=False)
    parser.add_argument("category")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--dry-run", action="store_true")
    mode_group.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    manager = BibTeXManager(Path(__file__).resolve().parent)
    manager.ensure_storage()
    renderer = CVRenderer(Path(__file__).resolve().parent, manager)
    importer = ImportManager(manager)

    parser = build_parser()
    args, extra_args = parser.parse_known_args()
    cli = CVCLI(manager, renderer, importer)

    if args.command:
        return cli.run(args.command, args.category, extra_args)
    return cli.repl()


if __name__ == "__main__":
    raise SystemExit(main())
