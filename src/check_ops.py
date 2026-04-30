from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .bibtex_ops import BibTeXManager, ParsedEntry
from .render_ops import CVRenderer


@dataclass
class CheckReport:
    configuration_issues: List[str] = field(default_factory=list)
    data_validity_errors: List[str] = field(default_factory=list)
    data_quality_warnings: List[str] = field(default_factory=list)
    template_coverage_warnings: List[str] = field(default_factory=list)

    def has_findings(self) -> bool:
        return any(
            [
                self.configuration_issues,
                self.data_validity_errors,
                self.data_quality_warnings,
                self.template_coverage_warnings,
            ]
        )


class ProjectChecker:
    def __init__(self, root_dir: Path, manager: BibTeXManager, renderer: CVRenderer):
        self.root_dir = Path(root_dir)
        self.manager = manager
        self.renderer = renderer

    def run(self, category: Optional[str] = None) -> CheckReport:
        report = CheckReport()
        report.configuration_issues.extend(self.check_configuration())
        report.data_validity_errors.extend(self.check_data_validity(category))
        report.data_quality_warnings.extend(self.check_duplicate_titles(category))
        config_issues, template_warnings = self.check_templates(category)
        report.configuration_issues.extend(config_issues)
        report.template_coverage_warnings.extend(template_warnings)
        return report

    def check_configuration(self) -> List[str]:
        issues: List[str] = []
        config = self.manager.config

        required_sections = ["categories", "required_fields", "template_name", "output_dir"]
        for section in required_sections:
            if section not in config:
                issues.append(f"Missing required configuration section '{section}' in config.json.")

        categories = config.get("categories")
        if not isinstance(categories, dict) or not categories:
            issues.append("Configuration section 'categories' must be a non-empty mapping.")
        else:
            for category, relative_path in categories.items():
                if not isinstance(relative_path, str) or not relative_path.strip():
                    issues.append(f"Category '{category}' must map to a non-empty file path.")
                    continue
                mapped_path = self.root_dir / relative_path
                if not mapped_path.exists():
                    issues.append(f"Category '{category}' points to missing file '{relative_path}'.")

        required_fields = config.get("required_fields")
        if not isinstance(required_fields, dict):
            issues.append("Configuration section 'required_fields' must be a mapping.")
        elif isinstance(categories, dict):
            for category in categories.keys():
                if category not in required_fields:
                    issues.append(f"Category '{category}' is missing a required_fields entry.")

        template_name = config.get("template_name")
        if not isinstance(template_name, str) or not template_name.strip():
            issues.append("Configuration key 'template_name' must be a non-empty string.")
        else:
            default_template = self.root_dir / "templates" / f"{template_name}.tex"
            if not default_template.exists():
                issues.append(f"Default template '{template_name}.tex' could not be found in templates/.")

        templates_dir = self.root_dir / "templates"
        if not templates_dir.exists():
            issues.append("Templates directory 'templates/' could not be found.")
        elif not any(templates_dir.glob("*.tex")):
            issues.append("No LaTeX templates were found in templates/.")

        output_dir = config.get("output_dir")
        if not isinstance(output_dir, str) or not output_dir.strip():
            issues.append("Configuration key 'output_dir' must be a non-empty string.")

        return issues

    def check_data_validity(self, category: Optional[str] = None) -> List[str]:
        try:
            return self.manager.lint_category(category) if category else self.manager.lint_all()
        except ValueError as exc:
            return [str(exc)]

    def check_duplicate_titles(self, category: Optional[str] = None) -> List[str]:
        warnings: List[str] = []
        grouped_entries = self._load_target_entries(category)
        for collection, entries in grouped_entries.items():
            seen: Dict[str, str] = {}
            for entry in entries:
                title = entry["fields"].get("title", "").strip()
                if not title:
                    continue
                normalized = " ".join(title.lower().split())
                if normalized in seen:
                    warnings.append(
                        f"Duplicate title '{title}' found in '{seen[normalized]}' and '{entry['cite_key']}' in '{collection}'."
                    )
                else:
                    seen[normalized] = entry["cite_key"]
        return warnings

    def check_templates(self, category: Optional[str] = None) -> tuple[List[str], List[str]]:
        config_issues: List[str] = []
        warnings: List[str] = []
        templates_dir = self.root_dir / "templates"
        if not templates_dir.exists():
            return config_issues, warnings

        for template_path in sorted(templates_dir.glob("*.tex")):
            try:
                template_text = template_path.read_text(encoding="utf-8")
                directives = self.renderer.parse_directives(template_text)
            except ValueError as exc:
                config_issues.append(f"Template '{template_path.name}': {exc}")
                continue

            for directive in directives:
                if category and directive.collection != category:
                    continue
                entries = self.manager.list_entries(directive.collection)
                warnings.extend(self._format_field_warnings(template_path.name, directive.collection, directive.format_string, entries))
                warnings.extend(self._sort_field_warnings(template_path.name, directive.collection, directive.sort, entries))

        return config_issues, warnings

    @staticmethod
    def _format_field_warnings(
        template_name: str,
        collection: str,
        format_string: str,
        entries: List[ParsedEntry],
    ) -> List[str]:
        placeholders: List[str] = []
        for placeholder in ProjectChecker.renderer_placeholders(format_string):
            if placeholder not in placeholders:
                placeholders.append(placeholder)

        warnings: List[str] = []
        for entry in entries:
            missing = [
                field_name
                for field_name in placeholders
                if field_name not in {"entry_type", "cite_key"} and not entry["fields"].get(field_name, "").strip()
            ]
            if missing:
                warnings.append(
                    f"Template '{template_name}' collection '{collection}' entry '{entry['cite_key']}' is missing format field(s): {', '.join(missing)}."
                )
        return warnings

    @staticmethod
    def _sort_field_warnings(
        template_name: str,
        collection: str,
        sort_rule: str,
        entries: List[ParsedEntry],
    ) -> List[str]:
        if sort_rule == "lastname":
            required_field = "author"
        elif sort_rule in {"year", "year_desc"}:
            required_field = "year"
        else:
            return []

        warnings: List[str] = []
        for entry in entries:
            if not entry["fields"].get(required_field, "").strip():
                warnings.append(
                    f"Template '{template_name}' collection '{collection}' sorts by '{sort_rule}', but entry '{entry['cite_key']}' is missing '{required_field}'."
                )
        return warnings

    def _load_target_entries(self, category: Optional[str]) -> Dict[str, List[ParsedEntry]]:
        if category:
            return {category: self.manager.list_entries(category)}
        return self.manager.load_entries()

    @staticmethod
    def renderer_placeholders(format_string: str) -> List[str]:
        import re

        return re.findall(r"<<([^>]+)>>", format_string)
