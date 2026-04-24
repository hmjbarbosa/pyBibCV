import json
import re
from pathlib import Path
from typing import Any, Dict, List, TypedDict, Union


DEFAULT_REQUIRED_FIELDS = {
    "publications": ["entry_type", "cite_key", "title", "author", "year"],
    "talks": ["entry_type", "cite_key", "title", "author", "year"],
    "service": ["entry_type", "cite_key", "title", "author", "year"],
    "grants": ["entry_type", "cite_key", "title", "author", "year"],
    "students": ["entry_type", "cite_key", "title", "author", "year"],
}


class ParsedEntry(TypedDict):
    entry_type: str
    cite_key: str
    fields: Dict[str, str]


class BibTeXManager:
    def __init__(self, root_dir: Union[Path, str]):
        self.root_dir = Path(root_dir)
        self.config_path = self.root_dir / "config.json"
        self.data_dir = self.root_dir / "data"
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def categories(self) -> List[str]:
        return list(self.config.get("categories", {}).keys())

    def category_path(self, category: str) -> Path:
        category_map = self.config.get("categories", {})
        if category not in category_map:
            raise ValueError(f"Unknown category '{category}'. Available: {', '.join(self.categories())}")
        return self.root_dir / category_map[category]

    def ensure_storage(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for category in self.categories():
            path = self.category_path(category)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)

    def add_entry(self, category: str, entry: Dict[str, str]) -> None:
        path = self.category_path(category)
        formatted = self.format_entry(entry)
        with path.open("a", encoding="utf-8") as handle:
            if path.stat().st_size > 0:
                handle.write("\n\n")
            handle.write(formatted)
            handle.write("\n")

    def list_entries(self, category: str) -> List[ParsedEntry]:
        path = self.category_path(category)
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return []

        blocks = re.split(r"\n\s*\n(?=@)", content)
        return [self.parse_entry(block) for block in blocks if block.strip()]

    def load_entries(self, categories: List[str] = None) -> Dict[str, List[ParsedEntry]]:
        selected_categories = categories if categories is not None else self.categories()
        grouped_entries: Dict[str, List[ParsedEntry]] = {}
        for category in selected_categories:
            grouped_entries[category] = self.list_entries(category)
        return grouped_entries

    def lint_category(self, category: str) -> List[str]:
        path = self.category_path(category)
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return []

        issues: List[str] = []
        blocks = re.split(r"\n\s*\n(?=@)", content)
        required_fields = self.config.get("required_fields", {}).get(
            category,
            DEFAULT_REQUIRED_FIELDS.get(category, []),
        )

        for index, block in enumerate(blocks, start=1):
            try:
                entry = self.parse_entry(block)
            except ValueError as exc:
                issues.append(f"{category} entry {index}: {exc}")
                continue

            for field in required_fields:
                if not str(entry["fields"].get(field, "")).strip():
                    issues.append(f"{category} entry {index}: missing required field '{field}'")

        return issues

    def lint_all(self) -> List[str]:
        issues: List[str] = []
        for category in self.categories():
            issues.extend(self.lint_category(category))
        return issues

    @staticmethod
    def parse_entry(block: str) -> ParsedEntry:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("@") or not lines[-1].strip().endswith("}"):
            raise ValueError("invalid BibTeX block structure")

        header_match = re.match(r"@(?P<entry_type>\w+)\{(?P<cite_key>[^,]+),", lines[0].strip())
        if not header_match:
            raise ValueError("invalid BibTeX header")

        fields: Dict[str, str] = {
            "entry_type": header_match.group("entry_type"),
            "cite_key": header_match.group("cite_key"),
        }

        for line in lines[1:-1]:
            field_match = re.match(r"(?P<field>\w+)\s*=\s*\{(?P<value>.*)\},?$", line.strip())
            if not field_match:
                raise ValueError(f"invalid field line '{line.strip()}'")
            fields[field_match.group("field")] = field_match.group("value").strip()

        return {
            "entry_type": fields["entry_type"],
            "cite_key": fields["cite_key"],
            "fields": fields,
        }

    @staticmethod
    def format_entry(entry: Dict[str, str]) -> str:
        entry_type = entry["entry_type"].strip()
        cite_key = entry["cite_key"].strip()
        field_lines = []

        for key, value in entry.items():
            if key in {"entry_type", "cite_key"}:
                continue
            cleaned = value.strip()
            if cleaned:
                field_lines.append(f"  {key} = {{{cleaned}}},")

        body = "\n".join(field_lines)
        return f"@{entry_type}{{{cite_key},\n{body}\n}}"
