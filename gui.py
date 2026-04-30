import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Dict, List, Optional

from src.bibtex_ops import BibTeXManager, ParsedEntry
from src.gui_controller import GUIController
from src.import_ops import DOIImportError


class EntryEditorDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        controller: GUIController,
        title: str,
        category: Optional[str] = None,
        entry: Optional[ParsedEntry] = None,
    ):
        super().__init__(master)
        self.controller = controller
        self.categories = controller.collections()
        self.original_entry = entry
        self.title(title)
        self.resizable(True, True)
        self.result = None
        self.transient(master)
        self.grab_set()

        self.category_var = tk.StringVar(value=category or (self.categories[0] if self.categories else ""))
        self.entry_type_var = tk.StringVar(value=entry["entry_type"] if entry else "")
        self.cite_key_var = tk.StringVar(value=entry["cite_key"] if entry else "")

        ttk.Label(self, text="Collection").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        category_state = "disabled" if entry else "readonly"
        self.category_box = ttk.Combobox(self, textvariable=self.category_var, values=self.categories, state=category_state)
        self.category_box.grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 4))
        self.category_box.bind("<<ComboboxSelected>>", self.on_category_changed)

        ttk.Label(self, text="Entry type").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.entry_type_box = ttk.Combobox(self, textvariable=self.entry_type_var)
        self.entry_type_box.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        self.entry_type_hint = ttk.Label(self, text="", foreground="#555555")
        self.entry_type_hint.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        ttk.Label(self, text="Cite key").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(self, textvariable=self.cite_key_var).grid(row=3, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(self, text="Fields (one per line: field=value)").grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))
        self.fields_text = ScrolledText(self, width=60, height=14)
        self.fields_text.grid(row=5, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)

        button_frame = ttk.Frame(self)
        button_frame.grid(row=6, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(button_frame, text="Save", command=self.on_save).pack(side="right")

        self.columnconfigure(1, weight=1)
        self.rowconfigure(5, weight=1)
        self.refresh_dynamic_fields()
        self.wait_visibility()
        self.focus_set()

    def on_save(self) -> None:
        try:
            self.result = self.parse_result()
        except ValueError as exc:
            messagebox.showerror("Invalid Entry", str(exc), parent=self)
            return
        self.destroy()

    def on_category_changed(self, event: object = None) -> None:
        if self.original_entry is not None:
            return
        self.refresh_dynamic_fields()

    def refresh_dynamic_fields(self) -> None:
        category = self.category_var.get().strip()
        if not category:
            return

        known_types = self.controller.known_entry_types(category)
        self.entry_type_box["values"] = known_types
        if known_types:
            self.entry_type_hint.config(text=f"Known entry types in this collection: {', '.join(known_types)}")
        else:
            self.entry_type_hint.config(text="No existing entry types found in this collection yet.")

        lines = self.build_field_lines(category)
        self.fields_text.delete("1.0", "end")
        self.fields_text.insert("1.0", "\n".join(lines))

    def build_field_lines(self, category: str) -> List[str]:
        required_fields = [
            field_name
            for field_name in self.controller.required_fields(category)
            if field_name not in {"entry_type", "cite_key"}
        ]
        entry_fields = self.original_entry["fields"] if self.original_entry else {}

        ordered_fields: List[str] = []
        for field_name in required_fields:
            ordered_fields.append(field_name)
        for field_name in entry_fields.keys():
            if field_name in {"entry_type", "cite_key"}:
                continue
            if field_name not in ordered_fields:
                ordered_fields.append(field_name)

        lines: List[str] = []
        for field_name in ordered_fields:
            lines.append(f"{field_name}={entry_fields.get(field_name, '')}")
        return lines

    def parse_result(self) -> Dict[str, object]:
        entry_type = self.entry_type_var.get().strip()
        cite_key = self.cite_key_var.get().strip()
        category = self.category_var.get().strip()
        if not category:
            raise ValueError("A collection is required.")
        if not entry_type:
            raise ValueError("Entry type is required.")
        if not cite_key:
            raise ValueError("Cite key is required.")

        entry = {"entry_type": entry_type, "cite_key": cite_key}
        remove_fields: List[str] = []
        for raw_line in self.fields_text.get("1.0", "end").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "=" not in line:
                raise ValueError(f"Invalid field line '{line}'. Use field=value.")
            field_name, value = line.split("=", 1)
            field_name = field_name.strip()
            value = value.strip()
            if not field_name:
                raise ValueError("Field names cannot be empty.")
            if value:
                entry[field_name] = value
            else:
                remove_fields.append(field_name)

        return {"category": category, "entry": entry, "remove_fields": remove_fields}


class BibTeXImportTextDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, categories: List[str], default_category: Optional[str] = None):
        super().__init__(master)
        self.title("Import BibTeX Text")
        self.result = None
        self.transient(master)
        self.grab_set()

        self.category_var = tk.StringVar(value=default_category or (categories[0] if categories else ""))
        ttk.Label(self, text="Collection").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Combobox(self, textvariable=self.category_var, values=categories, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=8, pady=(8, 4)
        )

        ttk.Label(self, text="BibTeX").grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))
        self.text = ScrolledText(self, width=70, height=16)
        self.text.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)

        button_frame = ttk.Frame(self)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(button_frame, text="Import", command=self.on_import).pack(side="right")

        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.wait_visibility()
        self.focus_set()

    def on_import(self) -> None:
        category = self.category_var.get().strip()
        content = self.text.get("1.0", "end").strip()
        if not category:
            messagebox.showerror("Missing Collection", "Choose a target collection.", parent=self)
            return
        if not content:
            messagebox.showerror("Missing BibTeX", "Paste BibTeX content before importing.", parent=self)
            return
        self.result = {"category": category, "content": content}
        self.destroy()


class DOIImportDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, categories: List[str], default_category: Optional[str] = None):
        super().__init__(master)
        self.title("Import DOI")
        self.result = None
        self.transient(master)
        self.grab_set()

        self.category_var = tk.StringVar(value=default_category or (categories[0] if categories else ""))
        self.doi_var = tk.StringVar()
        self.key_var = tk.StringVar()

        ttk.Label(self, text="Collection").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Combobox(self, textvariable=self.category_var, values=categories, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=8, pady=(8, 4)
        )
        ttk.Label(self, text="DOI").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(self, textvariable=self.doi_var).grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(self, text="Custom cite key (optional)").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(self, textvariable=self.key_var).grid(row=2, column=1, sticky="ew", padx=8, pady=4)

        button_frame = ttk.Frame(self)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(button_frame, text="Import", command=self.on_import).pack(side="right")
        self.columnconfigure(1, weight=1)

    def on_import(self) -> None:
        category = self.category_var.get().strip()
        doi = self.doi_var.get().strip()
        custom_key = self.key_var.get().strip()
        if not category:
            messagebox.showerror("Missing Collection", "Choose a target collection.", parent=self)
            return
        if not doi:
            messagebox.showerror("Missing DOI", "Enter a DOI before importing.", parent=self)
            return
        self.result = {"category": category, "doi": doi, "cite_key": custom_key or None}
        self.destroy()


class BibTeXImportFileDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, categories: List[str], default_category: Optional[str] = None):
        super().__init__(master)
        self.title("Import BibTeX File")
        self.result = None
        self.transient(master)
        self.grab_set()

        self.category_var = tk.StringVar(value=default_category or (categories[0] if categories else ""))
        self.path_var = tk.StringVar()

        ttk.Label(self, text="Collection").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Combobox(self, textvariable=self.category_var, values=categories, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=8, pady=(8, 4)
        )
        ttk.Label(self, text="Selected file").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(self, textvariable=self.path_var).grid(row=1, column=1, sticky="w", padx=8, pady=4)

        button_frame = ttk.Frame(self)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(button_frame, text="Load File", command=self.on_load).pack(side="right")
        self.columnconfigure(1, weight=1)

    def on_load(self) -> None:
        category = self.category_var.get().strip()
        if not category:
            messagebox.showerror("Missing Collection", "Choose a target collection.", parent=self)
            return
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Choose a BibTeX file",
            filetypes=[("BibTeX files", "*.bib"), ("All files", "*.*")],
        )
        if not file_path:
            return
        self.path_var.set(file_path)
        self.result = {"category": category, "file_path": file_path}
        self.destroy()


class PyBibCVApp:
    def __init__(self, root: tk.Tk, controller: GUIController):
        self.root = root
        self.controller = controller
        self.current_category: Optional[str] = None
        self.current_entry_key: Optional[str] = None
        self.current_entries: List[ParsedEntry] = []
        self.filtered_entries: List[ParsedEntry] = []
        self.current_entry_type_filter = "(all)"
        self.detail_dirty = False
        self._loading_detail = False
        self._suppress_selection_events = False
        self._pending_collection_index: Optional[int] = None
        self._ignore_collection_events_until_idle = False
        self._suppress_type_filter_event = False

        self.root.title("pyBibCV")
        self.root.geometry("1200x700")

        self._build_menu()
        self._build_layout()
        self.refresh_collections()

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Refresh Collections", command=self.refresh_collections)
        file_menu.add_command(label="Render CV", command=self.render_cv)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        entry_menu = tk.Menu(menu_bar, tearoff=False)
        entry_menu.add_command(label="Add Entry", command=self.add_entry)
        entry_menu.add_command(label="Import DOI", command=self.import_doi)
        entry_menu.add_command(label="Import BibTeX Text", command=self.import_bibtex_text)
        entry_menu.add_command(label="Import BibTeX File", command=self.import_bibtex_file)
        entry_menu.add_command(label="Check", command=self.run_check)
        menu_bar.add_cascade(label="Actions", menu=entry_menu)

        self.root.config(menu=menu_bar)

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=8)
        container.pack(fill="both", expand=True)

        toolbar = ttk.Frame(container)
        toolbar.pack(fill="x", pady=(0, 8))
        buttons = [
            ("Refresh", self.refresh_collections),
            ("Add", self.add_entry),
            ("Import DOI", self.import_doi),
            ("Import BibTeX Text", self.import_bibtex_text),
            ("Import BibTeX File", self.import_bibtex_file),
            ("Check", self.run_check),
            ("Render", self.render_cv),
            ("Quit", self.root.destroy),
        ]
        for label, command in buttons:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 6))

        vertical_panes = tk.PanedWindow(
            container,
            orient="vertical",
            sashrelief="raised",
            sashwidth=8,
            bd=0,
        )
        vertical_panes.pack(fill="both", expand=True)

        main_area = ttk.Frame(vertical_panes)
        output_area = ttk.Frame(vertical_panes)

        panes = ttk.Panedwindow(main_area, orient="horizontal")
        panes.pack(fill="both", expand=True)

        collection_frame = ttk.Labelframe(panes, text="Collections", padding=8)
        entry_frame = ttk.Labelframe(panes, text="Entries", padding=8)
        detail_frame = ttk.Labelframe(panes, text="Entry Details", padding=8)

        self.collection_list = tk.Listbox(collection_frame, exportselection=False)
        self.collection_list.pack(fill="both", expand=True)
        self.collection_list.bind("<<ListboxSelect>>", self.on_collection_selected)

        entry_controls = ttk.Frame(entry_frame)
        entry_controls.pack(fill="x", pady=(0, 6))
        ttk.Label(entry_controls, text="Entry Type").pack(side="left")
        self.entry_type_var = tk.StringVar(value="(all)")
        self.entry_type_box = ttk.Combobox(
            entry_controls,
            textvariable=self.entry_type_var,
            state="readonly",
            values=["(all)"],
            width=18,
        )
        self.entry_type_box.pack(side="left", padx=(8, 0))
        self.entry_type_box.bind("<<ComboboxSelected>>", self.on_entry_type_selected)

        self.entry_list = tk.Listbox(entry_frame, exportselection=False)
        self.entry_list.pack(fill="both", expand=True)
        self.entry_list.bind("<<ListboxSelect>>", self.on_entry_selected)

        detail_controls = ttk.Frame(detail_frame)
        detail_controls.pack(fill="x", pady=(0, 6))
        self.save_detail_button = ttk.Button(detail_controls, text="Save", command=self.save_detail_changes, state="disabled")
        self.save_detail_button.pack(side="right")

        self.detail_text = ScrolledText(detail_frame, wrap="word", state="disabled")
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.bind("<<Modified>>", self.on_detail_modified)

        panes.add(collection_frame, weight=1)
        panes.add(entry_frame, weight=2)
        panes.add(detail_frame, weight=3)

        output_frame = ttk.Labelframe(output_area, text="Output", padding=8)
        output_frame.pack(fill="both", expand=True)

        output_controls = ttk.Frame(output_frame)
        output_controls.pack(fill="x", pady=(0, 6))
        ttk.Button(output_controls, text="Clear", command=self.clear_output).pack(side="right")

        self.output_text = ScrolledText(output_frame, wrap="word", height=10, state="disabled")
        self.output_text.pack(fill="both", expand=True)

        vertical_panes.add(main_area, stretch="always", minsize=250)
        vertical_panes.add(output_area, minsize=120)

    def refresh_collections(self) -> None:
        collections = self.controller.collections()
        self.collection_list.delete(0, "end")
        for collection in collections:
            self.collection_list.insert("end", collection)

        if collections:
            target_index = 0
            if self.current_category in collections:
                target_index = collections.index(self.current_category)
            self.collection_list.selection_clear(0, "end")
            self.collection_list.selection_set(target_index)
            self.collection_list.event_generate("<<ListboxSelect>>")

    def on_collection_selected(self, event: object = None) -> None:
        if self._suppress_selection_events:
            return
        if self._pending_collection_index is not None:
            return
        if self._ignore_collection_events_until_idle:
            self.restore_collection_selection()
            return
        selection = self.collection_list.curselection()
        if not selection:
            return

        selected_index = selection[0]
        next_category = self.collection_list.get(selected_index)
        if next_category == self.current_category:
            return

        detail_snapshot = self.detail_text.get("1.0", "end")
        if next_category != self.current_category and not self.confirm_discard_unsaved():
            self._ignore_collection_events_until_idle = True
            if hasattr(self, "root") and hasattr(self.root, "after_idle"):
                self.root.after_idle(self.reset_collection_event_ignore)
            else:
                self._ignore_collection_events_until_idle = False
            self.restore_collection_selection()
            self.restore_dirty_detail_snapshot(detail_snapshot)
            return

        self._pending_collection_index = selected_index
        self.schedule_collection_selection(selected_index)

    def apply_collection_selection(self, selected_index: int) -> None:
        try:
            collections = self.controller.collections()
            if selected_index < 0 or selected_index >= len(collections):
                return

            next_category = collections[selected_index]
            self._suppress_selection_events = True
            self.collection_list.selection_clear(0, "end")
            self.collection_list.selection_set(selected_index)
            self._suppress_selection_events = False

            self.current_category = next_category
            self.current_entry_key = None
            self.current_entry_type_filter = "(all)"
            try:
                self.current_entries = self.controller.list_entries(self.current_category)
            except Exception as exc:
                self.show_error(str(exc))
                return

            self.populate_entry_type_filter()
            self.apply_entry_type_filter(refresh_detail=False)
            self.clear_detail()
        finally:
            self._pending_collection_index = None

    def on_entry_selected(self, event: object = None) -> None:
        if self._suppress_selection_events:
            return
        selection = self.entry_list.curselection()
        if not selection or not self.current_category:
            self.clear_detail()
            return

        selected_index = selection[0]
        visible_entries = getattr(self, "filtered_entries", self.current_entries)
        entry = visible_entries[selected_index]

        if entry["cite_key"] == self.current_entry_key:
            return

        detail_snapshot = self.detail_text.get("1.0", "end")
        if entry["cite_key"] != self.current_entry_key and not self.confirm_discard_unsaved():
            self.restore_entry_selection()
            self.restore_dirty_detail_snapshot(detail_snapshot)
            return

        self.schedule_entry_selection(selected_index)

    def clear_detail(self) -> None:
        self._loading_detail = True
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.config(state="disabled")
        self.detail_text.edit_modified(False)
        self._loading_detail = False
        self.detail_dirty = False
        self.save_detail_button.config(state="disabled")

    def show_entry_detail(self, entry: ParsedEntry) -> None:
        self._loading_detail = True
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", BibTeXManager.format_entry(entry["fields"]))
        self.detail_text.edit_modified(False)
        self._loading_detail = False
        self.detail_dirty = False
        self.save_detail_button.config(state="normal")

    def populate_entry_type_filter(self) -> None:
        if not hasattr(self, "entry_type_box") or not hasattr(self, "entry_type_var"):
            self.filtered_entries = list(self.current_entries)
            self.current_entry_type_filter = "(all)"
            return
        entry_types = ["(all)"]
        for entry in self.current_entries:
            entry_type = entry["entry_type"].strip()
            if entry_type and entry_type not in entry_types:
                entry_types.append(entry_type)

        self._suppress_type_filter_event = True
        self.entry_type_box["values"] = entry_types
        self.entry_type_var.set("(all)")
        self._suppress_type_filter_event = False

    def apply_entry_type_filter(self, refresh_detail: bool = True) -> None:
        if not hasattr(self, "entry_type_var"):
            self.filtered_entries = list(self.current_entries)
            return

        selected_type = self.entry_type_var.get().strip() or "(all)"
        self.current_entry_type_filter = selected_type
        if selected_type == "(all)":
            self.filtered_entries = list(self.current_entries)
        else:
            self.filtered_entries = [entry for entry in self.current_entries if entry["entry_type"].strip() == selected_type]

        self.entry_list.delete(0, "end")
        for entry in self.filtered_entries:
            fields = entry["fields"]
            label = f"{entry['cite_key']} | {fields.get('title', '(no title)')} | {fields.get('year', fields.get('date', ''))}"
            self.entry_list.insert("end", label)

        if not refresh_detail:
            return

        if self.current_entry_key:
            for index, entry in enumerate(self.filtered_entries):
                if entry["cite_key"] == self.current_entry_key:
                    self._suppress_selection_events = True
                    self.entry_list.selection_clear(0, "end")
                    self.entry_list.selection_set(index)
                    self._suppress_selection_events = False
                    return

        self.current_entry_key = None
        self.clear_detail()

    def on_entry_type_selected(self, event: object = None) -> None:
        if self._suppress_type_filter_event:
            return

        new_filter = self.entry_type_var.get().strip() or "(all)"
        if new_filter == self.current_entry_type_filter:
            return

        current_entry_still_visible = False
        if self.current_entry_key:
            for entry in self.current_entries:
                if entry["cite_key"] == self.current_entry_key:
                    current_entry_still_visible = new_filter == "(all)" or entry["entry_type"].strip() == new_filter
                    break

        detail_snapshot = self.detail_text.get("1.0", "end")
        if self.detail_dirty and not current_entry_still_visible and not self.confirm_discard_unsaved():
            self._suppress_type_filter_event = True
            self.entry_type_var.set(self.current_entry_type_filter)
            self._suppress_type_filter_event = False
            self.restore_dirty_detail_snapshot(detail_snapshot)
            return

        self.apply_entry_type_filter()

    def add_entry(self) -> None:
        dialog = EntryEditorDialog(self.root, self.controller, "Add Entry", category=self.current_category)
        self.root.wait_window(dialog)
        if not dialog.result:
            return

        payload = dialog.result
        try:
            saved = self.controller.add_entry(payload["category"], payload["entry"])
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.refresh_after_change(payload["category"], saved["cite_key"])
        self.write_output(f"Saved entry '{saved['cite_key']}' to '{payload['category']}'.")

    def import_doi(self) -> None:
        dialog = DOIImportDialog(self.root, self.controller.collections(), default_category=self.current_category)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        try:
            imported = self.controller.import_doi(
                dialog.result["category"],
                dialog.result["doi"],
                cite_key=dialog.result["cite_key"],
            )
        except DOIImportError as exc:
            self.show_error(str(exc))
            return
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.refresh_after_change(dialog.result["category"], imported["cite_key"])
        self.write_output("DOI Imported:")
        self.write_output(BibTeXManager.format_entry(imported["fields"]))

    def import_bibtex_text(self) -> None:
        dialog = BibTeXImportTextDialog(self.root, self.controller.collections(), default_category=self.current_category)
        self.root.wait_window(dialog)
        if not dialog.result:
            return

        try:
            imported_entries = self.controller.import_bibtex_string(dialog.result["category"], dialog.result["content"])
        except Exception as exc:
            self.show_error(str(exc))
            return
        final_key = imported_entries[-1]["cite_key"] if imported_entries else None
        self.refresh_after_change(dialog.result["category"], final_key)
        self.write_output(
            f"Imported {len(imported_entries)} entr{'y' if len(imported_entries) == 1 else 'ies'} into '{dialog.result['category']}'."
        )

    def import_bibtex_file(self) -> None:
        dialog = BibTeXImportFileDialog(self.root, self.controller.collections(), default_category=self.current_category)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        try:
            imported_entries = self.controller.import_bibtex_file(dialog.result["category"], dialog.result["file_path"])
        except Exception as exc:
            self.show_error(str(exc))
            return
        final_key = imported_entries[-1]["cite_key"] if imported_entries else None
        self.refresh_after_change(dialog.result["category"], final_key)
        self.write_output(
            f"Imported {len(imported_entries)} entr{'y' if len(imported_entries) == 1 else 'ies'} into '{dialog.result['category']}'."
        )

    def run_check(self) -> None:
        try:
            report = self.controller.check()
        except Exception as exc:
            self.show_error(str(exc))
            return

        if not report.has_findings():
            self.write_output("No check issues found.")
            return

        if report.configuration_issues:
            self.write_output("Configuration issues:")
            for issue in report.configuration_issues:
                self.write_output(f"- {issue}")

        if report.data_validity_errors:
            self.write_output("Data validity errors:")
            for issue in report.data_validity_errors:
                self.write_output(f"- {issue}")

        if report.data_quality_warnings:
            self.write_output("Data quality warnings:")
            for issue in report.data_quality_warnings:
                self.write_output(f"- {issue}")

        if report.template_coverage_warnings:
            self.write_output("Template coverage warnings:")
            for issue in report.template_coverage_warnings:
                self.write_output(f"- {issue}")

    def save_detail_changes(self) -> None:
        if not self.current_category or not self.current_entry_key:
            self.show_error("Select an entry before saving.")
            return

        raw_bibtex = self.detail_text.get("1.0", "end").strip()
        try:
            updated = self.controller.replace_entry_from_raw(self.current_category, self.current_entry_key, raw_bibtex)
        except Exception as exc:
            self.show_error(str(exc))
            return

        self.refresh_after_change(self.current_category, updated["cite_key"])
        self.write_output(f"Saved entry '{updated['cite_key']}' in '{self.current_category}'.")

    def render_cv(self) -> None:
        output_name = simpledialog.askstring("Render CV", "Output base name:", initialvalue="cv", parent=self.root)
        if output_name is None:
            return
        compile_pdf = messagebox.askyesno(
            "Render CV",
            "Try to compile a PDF after generating the .tex file?",
            parent=self.root,
        )
        try:
            result = self.controller.render(output_name=output_name.strip() or "cv", compile_pdf=compile_pdf)
        except Exception as exc:
            self.show_error(str(exc))
            return

        if result.compilation_log:
            self.write_output("LaTeX Compilation Output:")
            for line in result.compilation_log.splitlines():
                self.write_output(line)

        lines = [f"Generated TeX: {result.tex_path}"]
        if result.pdf_path:
            lines.append(f"Generated PDF: {result.pdf_path}")
        if result.compilation_message:
            lines.append(result.compilation_message)
        self.write_output("Render Complete:")
        for line in lines:
            self.write_output(line)

    def refresh_after_change(self, category: str, cite_key: Optional[str]) -> None:
        self.current_category = category
        self.current_entry_key = cite_key
        self.detail_dirty = False
        try:
            self.current_entries = self.controller.list_entries(category)
        except Exception as exc:
            self.show_error(str(exc))
            return

        self._suppress_selection_events = True
        self.collection_list.selection_clear(0, "end")
        collections = self.controller.collections()
        if category in collections:
            self.collection_list.selection_set(collections.index(category))
        self._suppress_selection_events = False

        self.populate_entry_type_filter()
        self.apply_entry_type_filter(refresh_detail=False)

        if not self.current_category:
            return

        for index, entry in enumerate(self.filtered_entries):
            if entry["cite_key"] == cite_key:
                self._suppress_selection_events = True
                self.entry_list.selection_clear(0, "end")
                self.entry_list.selection_set(index)
                self._suppress_selection_events = False
                self.show_entry_detail(entry)
                break

    def on_detail_modified(self, event: object = None) -> None:
        if self._loading_detail:
            return
        if self.detail_text.edit_modified():
            self.detail_dirty = True
            self.detail_text.edit_modified(False)

    def require_selected_entry(self) -> Optional[ParsedEntry]:
        if not self.current_category or not self.current_entry_key:
            messagebox.showinfo("Select Entry", "Select an entry first.", parent=self.root)
            return None
        try:
            return self.controller.get_entry(self.current_category, self.current_entry_key)
        except Exception as exc:
            self.show_error(str(exc))
            return None

    def ensure_category_selected(self) -> Optional[str]:
        if not self.current_category:
            messagebox.showinfo("Select Collection", "Select a collection first.", parent=self.root)
        return self.current_category

    def confirm_discard_unsaved(self) -> bool:
        if not self.detail_dirty:
            return True
        return messagebox.askyesno(
            "Unsaved Changes",
            "You have unsaved changes in Entry Details. Discard them?",
            parent=self.root,
        )

    def restore_collection_selection(self) -> None:
        self._suppress_selection_events = True
        self.collection_list.selection_clear(0, "end")
        if self.current_category is None:
            self._suppress_selection_events = False
            return
        collections = self.controller.collections()
        if self.current_category in collections:
            self.collection_list.selection_set(collections.index(self.current_category))
        self._suppress_selection_events = False

    def restore_entry_selection(self) -> None:
        visible_entries = getattr(self, "filtered_entries", self.current_entries)
        self._suppress_selection_events = True
        self.entry_list.selection_clear(0, "end")
        if self.current_entry_key is None:
            self._suppress_selection_events = False
            return
        for index, entry in enumerate(visible_entries):
            if entry["cite_key"] == self.current_entry_key:
                self.entry_list.selection_set(index)
                break
        self._suppress_selection_events = False

    def restore_dirty_detail_snapshot(self, detail_snapshot: str) -> None:
        if not self.detail_dirty:
            return
        self._loading_detail = True
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", detail_snapshot)
        self.detail_text.edit_modified(False)
        self._loading_detail = False
        self.detail_dirty = True
        self.save_detail_button.config(state="normal")

    def schedule_entry_selection(self, selected_index: int) -> None:
        if hasattr(self, "root") and hasattr(self.root, "after_idle"):
            self.root.after_idle(lambda: self.apply_entry_selection(selected_index))
            return
        self.apply_entry_selection(selected_index)

    def schedule_collection_selection(self, selected_index: int) -> None:
        if hasattr(self, "root") and hasattr(self.root, "after_idle"):
            self.root.after_idle(lambda: self.apply_collection_selection(selected_index))
            return
        self.apply_collection_selection(selected_index)

    def reset_collection_event_ignore(self) -> None:
        self._ignore_collection_events_until_idle = False

    def apply_entry_selection(self, selected_index: int) -> None:
        visible_entries = getattr(self, "filtered_entries", self.current_entries)
        if selected_index < 0 or selected_index >= len(visible_entries):
            return
        entry = visible_entries[selected_index]
        self._suppress_selection_events = True
        self.entry_list.selection_clear(0, "end")
        self.entry_list.selection_set(selected_index)
        self._suppress_selection_events = False
        self.current_entry_key = entry["cite_key"]
        self.show_entry_detail(entry)

    def show_error(self, message: str) -> None:
        messagebox.showerror("pyBibCV", message, parent=self.root)

    def write_output(self, message: str) -> None:
        self.output_text.config(state="normal")
        self.output_text.insert("end", message.rstrip() + "\n")
        self.output_text.see("end")
        self.output_text.config(state="disabled")

    def clear_output(self) -> None:
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")


def build_app(root_dir: Optional[Path] = None) -> tuple[tk.Tk, PyBibCVApp]:
    base_dir = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parent
    root = tk.Tk()
    controller = GUIController.from_root_dir(base_dir)
    app = PyBibCVApp(root, controller)
    return root, app


def main() -> int:
    root, _app = build_app()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
