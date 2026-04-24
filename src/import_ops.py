import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib import error, parse, request

from .bibtex_ops import BibTeXManager, ParsedEntry


class DOIImportError(Exception):
    pass


class ImportManager:
    def __init__(self, manager: BibTeXManager):
        self.manager = manager

    def import_doi(self, category: str, doi: str, requested_key: Optional[str] = None) -> ParsedEntry:
        metadata = self.fetch_doi_metadata(doi)
        entry = self.metadata_to_entry(doi, metadata, requested_key=requested_key)
        imported_entries = self.manager.import_entries(category, [entry])
        return imported_entries[0]

    def import_bibtex_file(self, category: str, file_path: str) -> List[ParsedEntry]:
        content = Path(file_path).read_text(encoding="utf-8")
        return self.import_bibtex_string(category, content)

    def import_bibtex_string(self, category: str, bibtex_string: str) -> List[ParsedEntry]:
        try:
            parsed_entries = self.manager.parse_entries(bibtex_string)
        except ValueError as exc:
            raise DOIImportError(f"Invalid BibTeX input: {exc}") from exc

        entries_to_import: List[Dict[str, str]] = []
        for parsed in parsed_entries:
            entries_to_import.append(dict(parsed["fields"]))
        return self.manager.import_entries(category, entries_to_import)

    def fetch_doi_metadata(self, doi: str) -> Dict[str, object]:
        encoded_doi = parse.quote(doi, safe="/")
        metadata_url = f"https://doi.org/{encoded_doi}"
        req = request.Request(
            metadata_url,
            headers={"Accept": "application/vnd.citationstyles.csl+json"},
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise DOIImportError(f"DOI lookup failed for '{doi}' with HTTP status {exc.code}.") from exc
        except error.URLError as exc:
            raise DOIImportError(f"DOI lookup failed for '{doi}': {exc.reason}.") from exc

    def metadata_to_entry(
        self,
        doi: str,
        metadata: Dict[str, object],
        requested_key: Optional[str] = None,
    ) -> Dict[str, str]:
        entry_type = self.map_entry_type(str(metadata.get("type", "")))
        authors = metadata.get("author", [])
        author_string = self.format_authors(authors if isinstance(authors, list) else [])
        title = self.extract_title(metadata)
        year = self.extract_year(metadata)
        entry: Dict[str, str] = {
            "entry_type": entry_type,
            "cite_key": requested_key or self.generate_cite_key(author_string, year, title),
            "title": title,
            "author": author_string or "Unknown Author",
            "year": year or "n.d.",
            "doi": self.manager.normalize_doi_value(doi),
        }

        container_title = self.extract_first_string(metadata.get("container-title"))
        if entry_type == "article" and container_title:
            entry["journal"] = container_title
        elif container_title:
            entry["booktitle"] = container_title

        volume = self.extract_first_string(metadata.get("volume"))
        issue = self.extract_first_string(metadata.get("issue"))
        pages = self.extract_first_string(metadata.get("page"))
        publisher = self.extract_first_string(metadata.get("publisher"))

        if volume:
            entry["volume"] = volume
        if issue:
            entry["number"] = issue
        if pages:
            entry["pages"] = pages
        if publisher and "publisher" not in entry:
            entry["publisher"] = publisher

        if requested_key:
            existing_keys = set(self.manager.all_cite_keys())
            if requested_key in existing_keys:
                raise DOIImportError(f"Requested cite key '{requested_key}' already exists.")

        return entry

    @staticmethod
    def map_entry_type(source_type: str) -> str:
        lowered = source_type.lower()
        if "journal" in lowered or "article" in lowered:
            return "article"
        if "proceeding" in lowered or "conference" in lowered:
            return "inproceedings"
        if "book" in lowered:
            return "book"
        return "misc"

    @staticmethod
    def extract_title(metadata: Dict[str, object]) -> str:
        title_value = metadata.get("title", "")
        return ImportManager.extract_first_string(title_value) or "Untitled"

    @staticmethod
    def extract_year(metadata: Dict[str, object]) -> str:
        for date_field in ["issued", "published-print", "published-online", "created"]:
            date_value = metadata.get(date_field)
            if isinstance(date_value, dict):
                date_parts = date_value.get("date-parts", [])
                if date_parts and isinstance(date_parts, list) and date_parts[0]:
                    return str(date_parts[0][0])
        return ""

    @staticmethod
    def extract_first_string(value: object) -> str:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
            return ""
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def format_authors(authors: List[object]) -> str:
        formatted: List[str] = []
        for author in authors:
            if not isinstance(author, dict):
                continue
            given = str(author.get("given", "")).strip()
            family = str(author.get("family", "")).strip()
            literal = str(author.get("literal", "")).strip()
            if literal:
                formatted.append(literal)
            elif given or family:
                formatted.append(" ".join(part for part in [given, family] if part))
        return " and ".join(formatted)

    def generate_cite_key(self, author: str, year: str, title: str) -> str:
        author_token = re.sub(r"[^a-z0-9]+", "", author.split(" and ")[0].split()[-1].lower()) if author else "entry"
        year_token = re.sub(r"[^0-9]+", "", year) or "nd"
        title_words = re.findall(r"[A-Za-z0-9]+", title.lower())
        title_token = title_words[0] if title_words else "item"
        base_key = f"{author_token}{year_token}{title_token}"
        return self.manager.make_unique_key(base_key, set(self.manager.all_cite_keys()))
