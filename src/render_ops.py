import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from .bibtex_ops import BibTeXManager, ParsedEntry


@dataclass
class RenderResult:
    tex_path: Path
    pdf_path: Optional[Path]
    compilation_message: str


class SectionSpec(TypedDict):
    category: str
    list: str
    format: str


class TemplateSpec(TypedDict):
    sections: Dict[str, SectionSpec]
    document_title: str
    author_name: str


class CVRenderer:
    def __init__(self, root_dir: Path, manager: BibTeXManager):
        self.root_dir = Path(root_dir)
        self.manager = manager
        self.config = manager.config
        self.template_name = self.config.get("template_name", "basic_cv")
        self.output_dir = self.root_dir / self.config.get("output_dir", "output")

    def render(
        self,
        template_name: Optional[str] = None,
        output_name: str = "cv",
        min_year: Optional[int] = None,
        keyword: Optional[str] = None,
        compile_pdf: bool = False,
    ) -> RenderResult:
        selected_template = template_name or self.template_name
        template_spec = self.load_template_spec(selected_template)
        grouped_entries = self.collect_sections(template_spec, min_year=min_year, keyword=keyword)
        tex_content = self.render_tex(selected_template, template_spec, grouped_entries)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        tex_path = self.output_dir / f"{output_name}.tex"
        tex_path.write_text(tex_content, encoding="utf-8")

        pdf_path = None
        compilation_message = "PDF compilation skipped."
        if compile_pdf:
            pdf_path, compilation_message = self.compile_pdf(tex_path)

        return RenderResult(tex_path=tex_path, pdf_path=pdf_path, compilation_message=compilation_message)

    def load_template_spec(self, template_name: str) -> TemplateSpec:
        template_spec_path = self.root_dir / "templates" / f"{template_name}.json"
        raw_spec = json.loads(template_spec_path.read_text(encoding="utf-8"))
        return {
            "sections": raw_spec.get("sections", {}),
            "document_title": raw_spec.get("document_title", "Curriculum Vitae"),
            "author_name": raw_spec.get("author_name", self.config.get("author_name", "Your Name")),
        }

    def collect_sections(
        self,
        template_spec: TemplateSpec,
        min_year: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for section_name, section_spec in template_spec["sections"].items():
            category = section_spec["category"]
            entries = self.manager.list_entries(category) if category in self.manager.categories() else []
            grouped[section_name] = {
                "spec": section_spec,
                "entries": self.filter_entries(entries, min_year=min_year, keyword=keyword),
            }
        return grouped

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

    def render_tex(
        self,
        template_name: str,
        template_spec: TemplateSpec,
        grouped_entries: Dict[str, Dict[str, Any]],
    ) -> str:
        template_path = self.root_dir / "templates" / f"{template_name}.tex"
        template = template_path.read_text(encoding="utf-8")
        sections_content = self.build_sections_content(grouped_entries)

        return (
            template.replace("<<DOCUMENT_TITLE>>", self.escape_latex(template_spec["document_title"]))
            .replace("<<AUTHOR_NAME>>", self.escape_latex(template_spec["author_name"]))
            .replace("<<GENERATED_ON>>", date.today().isoformat())
            .replace("<<SECTIONS_CONTENT>>", sections_content)
        )

    def build_sections_content(self, grouped_entries: Dict[str, Dict[str, Any]]) -> str:
        blocks: List[str] = []
        for section_name, section_data in grouped_entries.items():
            section_spec: SectionSpec = section_data["spec"]
            entries: List[ParsedEntry] = section_data["entries"]
            blocks.append("\\section*{" + self.escape_latex(section_name) + "}")
            if not entries:
                blocks.append("No entries available.\n")
                continue

            list_environment = self.resolve_list_environment(section_spec["list"])
            blocks.append("\\begin{" + list_environment + "}")
            for entry in entries:
                blocks.append("  \\item " + self.format_entry(entry, section_spec["format"]))
            blocks.append("\\end{" + list_environment + "}\n")
        return "\n".join(blocks)

    def format_entry(self, entry: ParsedEntry, format_string: str) -> str:
        fields = dict(entry["fields"])
        fields["entry_type"] = entry["entry_type"]
        fields["cite_key"] = entry["cite_key"]

        rendered_segments: List[str] = []
        for raw_segment in format_string.split(","):
            rendered_segment = raw_segment
            placeholders = re.findall(r"<<([^>]+)>>", raw_segment)
            for placeholder in placeholders:
                replacement = self.escape_latex(fields.get(placeholder, "").strip())
                rendered_segment = rendered_segment.replace(f"<<{placeholder}>>", replacement)
            rendered_segment = re.sub(r"\s+", " ", rendered_segment).strip()
            rendered_segment = re.sub(r"^[\s:;.-]+", "", rendered_segment)
            rendered_segment = re.sub(r"[\s:;.-]+$", "", rendered_segment)
            if rendered_segment:
                rendered_segments.append(rendered_segment)

        if not rendered_segments:
            return self.escape_latex(entry["cite_key"])
        return ", ".join(rendered_segments)

    def compile_pdf(self, tex_path: Path) -> Tuple[Optional[Path], str]:
        compiler = self.find_latex_compiler()
        if compiler is None:
            return None, "No LaTeX compiler was found. The .tex file was generated successfully."

        command = self.build_compile_command(compiler, tex_path)
        completed = subprocess.run(
            command,
            cwd=str(self.output_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            error_output = completed.stderr.strip() or completed.stdout.strip() or "Unknown LaTeX error."
            return None, f"LaTeX compilation failed: {error_output}"

        pdf_path = tex_path.with_suffix(".pdf")
        return pdf_path, f"PDF compilation succeeded using {compiler}."

    @staticmethod
    def build_compile_command(compiler: str, tex_path: Path) -> List[str]:
        filename = tex_path.name
        if compiler == "latexmk":
            return ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", filename]
        if compiler == "xelatex":
            return ["xelatex", "-interaction=nonstopmode", "-halt-on-error", filename]
        return [compiler, "-interaction=nonstopmode", "-halt-on-error", filename]

    @staticmethod
    def find_latex_compiler() -> Optional[str]:
        for compiler in ["latexmk", "xelatex", "pdflatex"]:
            if shutil.which(compiler):
                return compiler
        return None

    @staticmethod
    def resolve_list_environment(list_type: str) -> str:
        if list_type == "itemize":
            return "itemize"
        if list_type == "reverse-enumerate":
            return "etaremune"
        return "enumerate"

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
