import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .bibtex_ops import BibTeXManager, ParsedEntry


@dataclass
class RenderResult:
    tex_path: Path
    pdf_path: Optional[Path]
    compilation_message: str
    compilation_log: str


@dataclass
class CVListDirective:
    collection: str
    select: List[Tuple[str, str, str]]
    sort: str
    limit: Optional[int]
    list_type: str
    format_string: str
    raw: str
    start: int
    end: int


class CVRenderer:
    def __init__(self, root_dir: Path, manager: BibTeXManager):
        self.root_dir = Path(root_dir)
        self.manager = manager
        self.config = manager.config
        self.template_name = self.config.get("template_name", "basic_cv")
        self.output_dir = self.root_dir / self.config.get("output_dir", "output")
        self.latex_engine = self.config.get("latex_engine", "xelatex")

    def render(
        self,
        template_name: Optional[str] = None,
        output_name: str = "cv",
        min_year: Optional[int] = None,
        keyword: Optional[str] = None,
        compile_pdf: bool = False,
    ) -> RenderResult:
        selected_template = template_name or self.template_name
        tex_content = self.render_tex(selected_template, min_year=min_year, keyword=keyword)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        tex_path = self.output_dir / f"{output_name}.tex"
        tex_path.write_text(tex_content, encoding="utf-8")

        pdf_path = None
        compilation_message = "PDF compilation skipped."
        compilation_log = ""
        if compile_pdf:
            pdf_path, compilation_message, compilation_log = self.compile_pdf(tex_path)

        return RenderResult(
            tex_path=tex_path,
            pdf_path=pdf_path,
            compilation_message=compilation_message,
            compilation_log=compilation_log,
        )

    def render_tex(
        self,
        template_name: str,
        min_year: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> str:
        template_path = self.root_dir / "templates" / f"{template_name}.tex"
        template = template_path.read_text(encoding="utf-8")
        directives = self.parse_directives(template)

        rendered = template
        for directive in reversed(directives):
            replacement = self.render_directive(directive, min_year=min_year, keyword=keyword)
            rendered = rendered[: directive.start] + replacement + rendered[directive.end :]

        return (
            rendered.replace("<<DOCUMENT_TITLE>>", "Curriculum Vitae")
            .replace("<<AUTHOR_NAME>>", self.escape_latex(self.config.get("author_name", "Your Name")))
            .replace("<<GENERATED_ON>>", date.today().isoformat())
        )

    def parse_directives(self, template_text: str) -> List[CVListDirective]:
        directives: List[CVListDirective] = []
        pattern = r"\\CVList\["
        for match in re.finditer(pattern, template_text):
            start = match.start()
            open_bracket_index = match.end() - 1
            end = self.find_matching_bracket(template_text, open_bracket_index)
            options_text = template_text[open_bracket_index + 1 : end]
            directives.append(self.parse_directive(options_text, start, end + 1))
        return directives

    def parse_directive(self, options_text: str, start: int = 0, end: int = 0) -> CVListDirective:
        options = self.parse_option_pairs(options_text)
        required_options = {"collection", "sort", "list", "format"}
        missing = sorted(required_options - set(options.keys()))
        if missing:
            raise ValueError(f"CVList directive is missing required option(s): {', '.join(missing)}")

        unknown = sorted(set(options.keys()) - {"collection", "select", "sort", "limit", "list", "format"})
        if unknown:
            raise ValueError(f"CVList directive has unknown option(s): {', '.join(unknown)}")

        collection = options["collection"].strip()
        if collection not in self.manager.categories():
            raise ValueError(f"CVList directive references unknown collection '{collection}'.")

        select_rules = self.parse_select_expression(options.get("select", "all"))
        sort_value = options["sort"].strip()
        if sort_value not in {"year", "year_desc", "lastname"}:
            raise ValueError(f"CVList directive has invalid sort value '{sort_value}'.")

        list_value = options["list"].strip()
        if list_value not in {"itemize", "enumerate", "etaremune"}:
            raise ValueError(f"CVList directive has invalid list value '{list_value}'.")

        limit_value: Optional[int] = None
        if "limit" in options:
            try:
                limit_value = int(options["limit"])
            except ValueError as exc:
                raise ValueError(f"CVList directive has invalid limit value '{options['limit']}'.") from exc
            if limit_value <= 0:
                raise ValueError(f"CVList directive has invalid limit value '{options['limit']}'.")

        format_string = self.strip_quoted_string(options["format"])

        return CVListDirective(
            collection=collection,
            select=select_rules,
            sort=sort_value,
            limit=limit_value,
            list_type=list_value,
            format_string=format_string,
            raw=options_text,
            start=start,
            end=end,
        )

    def parse_option_pairs(self, options_text: str) -> Dict[str, str]:
        items = self.split_top_level(options_text, ",")
        options: Dict[str, str] = {}
        for item in items:
            if not item.strip():
                continue
            if "=" not in item:
                raise ValueError(f"Malformed CVList option '{item.strip()}'. Expected name=value.")
            name, value = item.split("=", 1)
            option_name = name.strip()
            if not option_name:
                raise ValueError(f"Malformed CVList option '{item.strip()}'.")
            options[option_name] = value.strip()
        return options

    def parse_select_expression(self, expression: str) -> List[Tuple[str, str, str]]:
        expr = expression.strip()
        if not expr or expr == "all":
            return []

        rules: List[Tuple[str, str, str]] = []
        for part in self.split_top_level(expr, ";"):
            candidate = part.strip()
            if not candidate:
                continue
            field_match = re.fullmatch(r"field\(([^,]+),(.+)\)", candidate)
            if field_match:
                rules.append(("field", field_match.group(1).strip(), field_match.group(2).strip()))
                continue
            after_match = re.fullmatch(r"after\((\d{4})\)", candidate)
            if after_match:
                rules.append(("after", "year", after_match.group(1)))
                continue
            raise ValueError(f"CVList directive has invalid select expression '{candidate}'.")
        return rules

    def render_directive(
        self,
        directive: CVListDirective,
        min_year: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> str:
        entries = self.manager.list_entries(directive.collection)
        filtered = self.apply_select_rules(entries, directive.select)
        filtered = self.filter_entries(filtered, min_year=min_year, keyword=keyword)
        filtered = self.sort_entries(filtered, directive.sort)
        if directive.limit is not None:
            filtered = filtered[: directive.limit]

        if not filtered:
            return "No entries available.\n"

        lines = [f"\\begin{{{directive.list_type}}}"]
        for entry in filtered:
            lines.append(f"  \\item {self.format_entry(entry, directive.format_string)}")
        lines.append(f"\\end{{{directive.list_type}}}")
        return "\n".join(lines)

    def apply_select_rules(self, entries: List[ParsedEntry], rules: List[Tuple[str, str, str]]) -> List[ParsedEntry]:
        filtered = list(entries)
        for rule_type, name, value in rules:
            if rule_type == "field":
                filtered = [
                    entry
                    for entry in filtered
                    if entry["fields"].get(name, "").strip().lower() == value.strip().lower()
                ]
            elif rule_type == "after":
                threshold = int(value)
                filtered = [
                    entry
                    for entry in filtered
                    if entry["fields"].get("year", "").strip().isdigit()
                    and int(entry["fields"].get("year", "0")) > threshold
                ]
        return filtered

    @staticmethod
    def filter_entries(
        entries: List[ParsedEntry],
        min_year: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> List[ParsedEntry]:
        filtered: List[ParsedEntry] = []
        lowered_keyword = keyword.lower() if keyword else None

        for entry in entries:
            fields = entry["fields"]
            if min_year is not None:
                year_value = fields.get("year", "").strip()
                if not year_value.isdigit() or int(year_value) < min_year:
                    continue

            if lowered_keyword is not None:
                combined_text = " ".join(fields.values()).lower()
                if lowered_keyword not in combined_text:
                    continue

            filtered.append(entry)

        return filtered

    def sort_entries(self, entries: List[ParsedEntry], sort_rule: str) -> List[ParsedEntry]:
        if sort_rule == "year":
            return sorted(entries, key=lambda entry: self.safe_year(entry))
        if sort_rule == "year_desc":
            return sorted(entries, key=lambda entry: self.safe_year(entry), reverse=True)
        return sorted(entries, key=lambda entry: self.author_last_name(entry))

    @staticmethod
    def safe_year(entry: ParsedEntry) -> int:
        year_value = entry["fields"].get("year", "").strip()
        return int(year_value) if year_value.isdigit() else -1

    @staticmethod
    def author_last_name(entry: ParsedEntry) -> str:
        author_value = entry["fields"].get("author", "").strip()
        if not author_value:
            return ""
        first_author = author_value.split(" and ")[0].strip()
        if "," in first_author:
            return first_author.split(",", 1)[0].strip().lower()
        parts = first_author.split()
        return parts[-1].strip().lower() if parts else ""

    def format_entry(self, entry: ParsedEntry, format_string: str) -> str:
        fields = dict(entry["fields"])
        fields["entry_type"] = entry["entry_type"]
        fields["cite_key"] = entry["cite_key"]

        rendered = format_string
        placeholders = re.findall(r"<<([^>]+)>>", format_string)
        for placeholder in placeholders:
            replacement = self.escape_latex(fields.get(placeholder, "").strip())
            rendered = rendered.replace(f"<<{placeholder}>>", replacement)

        rendered = re.sub(r"\s+", " ", rendered)
        rendered = re.sub(r"\s+([,;:.])", r"\1", rendered)
        rendered = re.sub(r",\s*,+", ", ", rendered)
        rendered = re.sub(r";\s*;+", "; ", rendered)
        rendered = re.sub(r":\s*:+", ": ", rendered)
        rendered = re.sub(r"\(\s*\)", "", rendered)
        rendered = re.sub(r"\s+\.", ".", rendered)
        rendered = re.sub(r"\s+,", ",", rendered)
        return rendered.strip(" ,;")

    def compile_pdf(self, tex_path: Path) -> Tuple[Optional[Path], str, str]:
        compiler = self.find_latex_compiler(self.latex_engine)
        if compiler is None:
            return None, "No LaTeX compiler was found. The .tex file was generated successfully.", ""

        command = self.build_compile_command(compiler, tex_path)
        completed = subprocess.run(
            command,
            cwd=str(self.output_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        log_output = self.format_compilation_log(command, completed.stdout, completed.stderr)
        if completed.returncode != 0:
            error_output = completed.stderr.strip() or completed.stdout.strip() or "Unknown LaTeX error."
            return None, f"LaTeX compilation failed: {error_output}", log_output

        pdf_path = tex_path.with_suffix(".pdf")
        return pdf_path, f"PDF compilation succeeded using {compiler}.", log_output

    @staticmethod
    def build_compile_command(compiler: str, tex_path: Path) -> List[str]:
        filename = tex_path.name
        if compiler == "latexmk":
            return ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", filename]
        if compiler == "xelatex":
            return ["xelatex", "-interaction=nonstopmode", "-halt-on-error", filename]
        return [compiler, "-interaction=nonstopmode", "-halt-on-error", filename]

    @staticmethod
    def format_compilation_log(command: List[str], stdout: str, stderr: str) -> str:
        lines = [f"$ {' '.join(command)}"]
        if stdout.strip():
            lines.append(stdout.rstrip())
        if stderr.strip():
            lines.append("[stderr]")
            lines.append(stderr.rstrip())
        return "\n".join(lines).strip()

    @staticmethod
    def find_latex_compiler(preferred_compiler: str = "xelatex") -> Optional[str]:
        compilers: List[str] = []
        if preferred_compiler:
            compilers.append(preferred_compiler)
        for compiler in ["xelatex", "latexmk", "pdflatex"]:
            if compiler not in compilers:
                compilers.append(compiler)
        for compiler in compilers:
            if shutil.which(compiler):
                return compiler
        return None

    @staticmethod
    def split_top_level(text: str, delimiter: str) -> List[str]:
        items: List[str] = []
        current: List[str] = []
        quote_char: Optional[str] = None
        paren_depth = 0
        for char in text:
            if quote_char:
                current.append(char)
                if char == quote_char:
                    quote_char = None
                continue

            if char in {'"', "'"}:
                quote_char = char
                current.append(char)
                continue

            if char == "(":
                paren_depth += 1
                current.append(char)
                continue

            if char == ")":
                paren_depth = max(paren_depth - 1, 0)
                current.append(char)
                continue

            if char == delimiter and paren_depth == 0:
                items.append("".join(current).strip())
                current = []
                continue

            current.append(char)

        if current:
            items.append("".join(current).strip())
        return items

    @staticmethod
    def find_matching_bracket(text: str, open_bracket_index: int) -> int:
        quote_char: Optional[str] = None
        for index in range(open_bracket_index + 1, len(text)):
            char = text[index]
            if quote_char:
                if char == quote_char:
                    quote_char = None
                continue
            if char in {'"', "'"}:
                quote_char = char
                continue
            if char == "]":
                return index
        raise ValueError("Malformed CVList directive: missing closing ']'.")

    @staticmethod
    def strip_quoted_string(value: str) -> str:
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
            return stripped[1:-1]
        return stripped

    @staticmethod
    def escape_latex(value: str) -> str:
        replacements = {
            "\\": "\\textbackslash{}",
            "&": "\\&",
            "%": "\\%",
            "$": "\\$",
            "#": "\\#",
            "_": "\\_",
            "{": "\\{",
            "}": "\\}",
        }
        escaped = value
        for source, target in replacements.items():
            escaped = escaped.replace(source, target)
        return escaped
