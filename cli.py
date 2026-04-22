import argparse
import shlex
from pathlib import Path
from typing import List, Optional

from bibtex_ops import BibTeXManager
from render_ops import CVRenderer, RenderResult


class CVCLI:
    def __init__(self, manager: BibTeXManager, renderer: CVRenderer):
        self.manager = manager
        self.renderer = renderer

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
        entry = {
            "entry_type": input("Entry type (e.g., article, inproceedings, misc): ").strip(),
            "cite_key": input("Citation key: ").strip(),
            "title": input("Title: ").strip(),
            "author": input("Author(s): ").strip(),
            "year": input("Year: ").strip(),
        }

        while True:
            field_name = input("Extra field name (press Enter to finish): ").strip()
            if not field_name:
                break
            entry[field_name] = input(f"Value for {field_name}: ").strip()

        self.manager.add_entry(category, entry)
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

    def repl(self) -> int:
        self.print_help()
        while True:
            raw = input("pyBibCV> ").strip()
            if not raw:
                continue
            parts = shlex.split(raw)
            command = parts[0]
            category = parts[1] if len(parts) > 1 and not parts[1].startswith("-") else None
            option_start = 2 if category else 1
            should_exit = self.run(command, category, parts[option_start:])
            if should_exit == 1:
                return 0

    def print_help(self) -> None:
        print("Commands:")
        print("  add <category>  - prompt for entry fields and append a BibTeX entry")
        print("  list <category> - display all entries in a category")
        print("  lint [category] - validate one category or all configured BibTeX files")
        print("  render [options] - build a LaTeX CV and optionally compile a PDF")
        print("  help            - show this message")
        print("  exit            - quit interactive mode")

    @staticmethod
    def print_render_result(result: RenderResult) -> None:
        print(f"Generated TeX: {result.tex_path}")
        if result.pdf_path:
            print(f"Generated PDF: {result.pdf_path}")
        if result.compilation_message:
            print(result.compilation_message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage CV-related BibTeX data.")
    parser.add_argument("command", nargs="?", help="Command to run: add, list, lint, render")
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


def main() -> int:
    manager = BibTeXManager(Path(__file__).resolve().parent)
    manager.ensure_storage()
    renderer = CVRenderer(Path(__file__).resolve().parent, manager)

    parser = build_parser()
    args, extra_args = parser.parse_known_args()
    cli = CVCLI(manager, renderer)

    if args.command:
        return cli.run(args.command, args.category, extra_args)
    return cli.repl()


if __name__ == "__main__":
    raise SystemExit(main())
