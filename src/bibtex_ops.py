import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union


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


class NormalizationChange(TypedDict):
    cite_key: str
    field: str
    action: str
    old: str
    new: str


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

    def required_fields_for_category(self, category: str) -> List[str]:
        self.category_path(category)
        return list(
            self.config.get("required_fields", {}).get(
                category,
                DEFAULT_REQUIRED_FIELDS.get(category, []),
            )
        )

    def known_entry_types(self, category: str) -> List[str]:
        self.category_path(category)
        known_types: List[str] = []
        for entry in self.list_entries(category):
            entry_type = entry["entry_type"].strip()
            if entry_type and entry_type not in known_types:
                known_types.append(entry_type)
        return known_types

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
        self._validate_duplicate_doi(category, entry)
        path = self.category_path(category)
        formatted = self.format_entry(entry)
        with path.open("a", encoding="utf-8") as handle:
            if path.stat().st_size > 0:
                handle.write("\n\n")
            handle.write(formatted)
            handle.write("\n")

    def list_entries(self, category: str) -> List[ParsedEntry]:
        path = self.category_path(category)
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return []
        return self.parse_entries(content)

    def load_entries(self, categories: Optional[List[str]] = None) -> Dict[str, List[ParsedEntry]]:
        selected_categories = categories if categories is not None else self.categories()
        grouped_entries: Dict[str, List[ParsedEntry]] = {}
        for category in selected_categories:
            grouped_entries[category] = self.list_entries(category)
        return grouped_entries

    def get_entry(self, category: str, cite_key: str) -> ParsedEntry:
        for entry in self.list_entries(category):
            if entry["cite_key"] == cite_key:
                return entry
        raise ValueError(f"Entry '{cite_key}' was not found in '{category}'.")

    def update_entry(
        self,
        category: str,
        cite_key: str,
        set_fields: Dict[str, str],
        remove_fields: List[str],
    ) -> ParsedEntry:
        entries = self.list_entries(category)
        updated_entry: Optional[ParsedEntry] = None

        for entry in entries:
            if entry["cite_key"] != cite_key:
                continue

            fields = dict(entry["fields"])
            for field, value in set_fields.items():
                if field == "entry_type":
                    entry["entry_type"] = value
                elif field == "cite_key":
                    entry["cite_key"] = value
                    fields["cite_key"] = value
                else:
                    fields[field] = value

            for field in remove_fields:
                if field in {"entry_type", "cite_key"}:
                    raise ValueError(f"Cannot remove required structural field '{field}'.")
                fields.pop(field, None)

            entry["fields"] = fields
            updated_entry = entry
            break

        if updated_entry is None:
            raise ValueError(f"Entry '{cite_key}' was not found in '{category}'.")

        self._validate_duplicate_doi(category, updated_entry["fields"], ignore_cite_key=updated_entry["cite_key"])
        self._rewrite_category(category, entries)
        return updated_entry

    def import_entries(self, category: str, entries: List[Dict[str, str]]) -> List[ParsedEntry]:
        existing_entries = self.list_entries(category)
        existing_keys = {entry["cite_key"] for entry in existing_entries}
        imported: List[ParsedEntry] = []

        for raw_entry in entries:
            candidate = dict(raw_entry)
            base_key = candidate["cite_key"]
            if candidate["cite_key"] in existing_keys:
                candidate["cite_key"] = self.make_unique_key(base_key, existing_keys)
            self._validate_duplicate_doi(category, candidate)
            existing_keys.add(candidate["cite_key"])
            existing_entries.append(self.parse_entry(self.format_entry(candidate)))
            imported.append(existing_entries[-1])

        self._rewrite_category(category, existing_entries)
        return imported

    def normalize_collection(
        self,
        category: str,
        dry_run: bool = True,
    ) -> Tuple[List[NormalizationChange], List[str]]:
        entries = self.list_entries(category)
        changes: List[NormalizationChange] = []

        for entry in entries:
            fields = dict(entry["fields"])
            entry_changes = self._normalize_entry_fields(category, fields)
            changes.extend(entry_changes)
            entry["fields"] = fields

        if not dry_run and changes:
            self._rewrite_category(category, entries)

        return changes, []

    def lint_category(self, category: str) -> List[str]:
        entries = self.list_entries(category)
        issues = self._lint_entries(category, entries)
        issues.extend(self._duplicate_key_issues({category: entries}, scope="category"))
        issues.extend(self._duplicate_doi_issues({category: entries}))
        return issues

    def lint_all(self) -> List[str]:
        grouped_entries = self.load_entries()
        issues: List[str] = []
        for category, entries in grouped_entries.items():
            issues.extend(self._lint_entries(category, entries))
        issues.extend(self._duplicate_key_issues(grouped_entries, scope="all categories"))
        issues.extend(self._duplicate_doi_issues(grouped_entries))
        return issues

    def expected_render_fields(self, category: str) -> List[str]:
        template_name = self.config.get("template_name", "basic_cv")
        template_path = self.root_dir / "templates" / f"{template_name}.tex"
        if not template_path.exists():
            return []

        template_text = template_path.read_text(encoding="utf-8")
        expected_fields: List[str] = []
        for options_text in re.findall(r"\\CVList\[(.*?)\]", template_text, flags=re.DOTALL):
            collection_match = re.search(r"collection\s*=\s*([^,\]]+)", options_text)
            if not collection_match or collection_match.group(1).strip() != category:
                continue
            format_match = re.search(r'format\s*=\s*"([^"]*)"', options_text, flags=re.DOTALL)
            if not format_match:
                continue
            placeholders = re.findall(r"<<([^>]+)>>", format_match.group(1))
            for placeholder in placeholders:
                if placeholder not in expected_fields:
                    expected_fields.append(placeholder)
        return expected_fields

    def all_cite_keys(self) -> List[str]:
        keys: List[str] = []
        for entries in self.load_entries().values():
            for entry in entries:
                keys.append(entry["cite_key"])
        return keys

    @staticmethod
    def split_bibtex_entries(content: str) -> List[str]:
        entries: List[str] = []
        current: List[str] = []
        brace_depth = 0
        started = False

        for char in content:
            if char == "@" and not started:
                started = True
                current = [char]
                brace_depth = 0
                continue

            if not started:
                continue

            current.append(char)
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth <= 0:
                    entries.append("".join(current).strip())
                    current = []
                    started = False
                    brace_depth = 0

        if started and "".join(current).strip():
            raise ValueError("unterminated BibTeX entry")

        return [entry for entry in entries if entry]

    @classmethod
    def parse_entries(cls, content: str) -> List[ParsedEntry]:
        return [cls.parse_entry(block) for block in cls.split_bibtex_entries(content)]

    @staticmethod
    def parse_entry(block: str) -> ParsedEntry:
        stripped_block = block.strip()
        if not stripped_block.startswith("@") or not stripped_block.endswith("}"):
            raise ValueError("invalid BibTeX block structure")

        header_match = re.match(r"@(?P<entry_type>\w+)\{(?P<cite_key>[^,]+),(?P<body>.*)\}\s*$", stripped_block, re.DOTALL)
        if not header_match:
            raise ValueError("invalid BibTeX header")

        body = header_match.group("body")
        fields: Dict[str, str] = {
            "entry_type": header_match.group("entry_type"),
            "cite_key": header_match.group("cite_key"),
        }
        position = 0

        while position < len(body):
            while position < len(body) and body[position] in " \n\r\t,":
                position += 1
            if position >= len(body):
                break

            field_match = re.match(r"(?P<field>\w+)\s*=\s*\{", body[position:])
            if not field_match:
                problematic = body[position:].strip().splitlines()[0] if body[position:].strip() else body[position:]
                raise ValueError(f"invalid field line '{problematic}'")

            field_name = field_match.group("field")
            position += field_match.end()
            value_start = position
            brace_depth = 1
            while position < len(body) and brace_depth > 0:
                if body[position] == "{":
                    brace_depth += 1
                elif body[position] == "}":
                    brace_depth -= 1
                position += 1

            if brace_depth != 0:
                raise ValueError(f"unterminated value for field '{field_name}'")

            field_value = body[value_start : position - 1].strip()
            fields[field_name] = field_value

        return {
            "entry_type": fields["entry_type"],
            "cite_key": fields["cite_key"],
            "fields": fields,
        }

    @staticmethod
    def format_entry(entry: Dict[str, str]) -> str:
        entry_type = entry["entry_type"].strip()
        cite_key = entry["cite_key"].strip()
        field_lines: List[str] = []

        for key, value in entry.items():
            if key in {"entry_type", "cite_key"}:
                continue
            cleaned = value.strip()
            if cleaned:
                field_lines.append(f"  {key} = {{{cleaned}}},")

        body = "\n".join(field_lines)
        return f"@{entry_type}{{{cite_key},\n{body}\n}}"

    @staticmethod
    def make_unique_key(base_key: str, existing_keys: set) -> str:
        suffix = 2
        candidate = base_key
        while candidate in existing_keys:
            candidate = f"{base_key}_{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def normalize_doi_value(value: str) -> str:
        cleaned = value.strip().lower()
        cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned)
        return cleaned

    def _rewrite_category(self, category: str, entries: List[ParsedEntry]) -> None:
        path = self.category_path(category)
        formatted_entries = [self.format_entry(entry["fields"]) for entry in entries]
        content = "\n\n".join(formatted_entries)
        if content:
            content += "\n"
        path.write_text(content, encoding="utf-8")

    def _validate_duplicate_doi(
        self,
        category: str,
        entry: Dict[str, str],
        ignore_cite_key: Optional[str] = None,
    ) -> None:
        doi_value = entry.get("doi", "").strip()
        if category != "publications" or not doi_value:
            return

        normalized = self.normalize_doi_value(doi_value)
        for existing in self.list_entries(category):
            if ignore_cite_key is not None and existing["cite_key"] == ignore_cite_key:
                continue
            existing_doi = self.normalize_doi_value(existing["fields"].get("doi", ""))
            if existing_doi and existing_doi == normalized:
                raise ValueError(
                    f"Duplicate DOI '{doi_value}' matches existing entry '{existing['cite_key']}' in '{category}'."
                )

    def _lint_entries(self, category: str, entries: List[ParsedEntry]) -> List[str]:
        issues: List[str] = []
        required_fields = self.config.get("required_fields", {}).get(
            category,
            DEFAULT_REQUIRED_FIELDS.get(category, []),
        )

        for index, entry in enumerate(entries, start=1):
            try:
                parsed_entry = self.parse_entry(self.format_entry(entry["fields"]))
            except ValueError as exc:
                issues.append(f"{category} entry {index}: {exc}")
                continue

            for field in required_fields:
                if not str(parsed_entry["fields"].get(field, "")).strip():
                    issues.append(f"{category} entry {index}: missing required field '{field}'")

            date_value = parsed_entry["fields"].get("date", "").strip()
            if date_value and not re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", date_value):
                issues.append(f"{category} entry {index}: malformed date '{date_value}'")

        return issues

    def _duplicate_key_issues(self, grouped_entries: Dict[str, List[ParsedEntry]], scope: str) -> List[str]:
        seen: Dict[str, str] = {}
        issues: List[str] = []
        for category, entries in grouped_entries.items():
            for entry in entries:
                cite_key = entry["cite_key"]
                if cite_key in seen:
                    issues.append(
                        f"Duplicate cite key '{cite_key}' found in '{seen[cite_key]}' and '{category}' while linting {scope}."
                    )
                else:
                    seen[cite_key] = category
        return issues

    def _duplicate_doi_issues(self, grouped_entries: Dict[str, List[ParsedEntry]]) -> List[str]:
        seen: Dict[str, str] = {}
        issues: List[str] = []
        entries = grouped_entries.get("publications", [])
        for entry in entries:
            doi = self.normalize_doi_value(entry["fields"].get("doi", ""))
            if not doi:
                continue
            if doi in seen:
                issues.append(
                    f"Duplicate DOI '{doi}' found in publication entries '{seen[doi]}' and '{entry['cite_key']}'."
                )
            else:
                seen[doi] = entry["cite_key"]
        return issues

    def _normalize_entry_fields(self, category: str, fields: Dict[str, str]) -> List[NormalizationChange]:
        cite_key = fields["cite_key"]
        changes: List[NormalizationChange] = []

        doi_value = fields.get("doi", "").strip()
        if doi_value:
            normalized_doi = self.normalize_doi_value(doi_value)
            if normalized_doi != doi_value:
                changes.append(
                    {"cite_key": cite_key, "field": "doi", "action": "set", "old": doi_value, "new": normalized_doi}
                )
                fields["doi"] = normalized_doi

        date_value = fields.get("date", "").strip()
        year_value = fields.get("year", "").strip()
        if date_value and not year_value:
            match = re.match(r"^(\d{4})", date_value)
            if match:
                changes.append(
                    {"cite_key": cite_key, "field": "year", "action": "set", "old": "", "new": match.group(1)}
                )
                fields["year"] = match.group(1)

        if category == "talks":
            venue_value = fields.get("venue", "").strip()
            note_value = fields.get("note", "").strip()
            if venue_value and not note_value:
                changes.append(
                    {"cite_key": cite_key, "field": "note", "action": "set", "old": "", "new": venue_value}
                )
                changes.append(
                    {
                        "cite_key": cite_key,
                        "field": "venue",
                        "action": "remove",
                        "old": venue_value,
                        "new": "",
                    }
                )
                fields["note"] = venue_value
                fields.pop("venue", None)

        return changes
