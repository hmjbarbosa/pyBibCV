# pyBibCV

`pyBibCV` is a Python command-line tool for managing CV data in BibTeX files and rendering that data into a basic LaTeX CV.

## Current project structure

- `cli.py`: command-line interface and interactive prompt
- `gui.py`: Tkinter desktop application entry point
- `src/bibtex_ops.py`: BibTeX parsing, formatting, loading, and linting
- `src/gui_controller.py`: thin controller layer shared by the Tkinter GUI and GUI-focused tests
- `src/import_ops.py`: DOI import and BibTeX import helpers
- `src/render_ops.py`: CV section grouping, filtering, LaTeX rendering, and optional PDF compilation
- `config.json`: app-level settings such as category file paths, required fields, the default template name, output settings, and author defaults
- `data/`: source `.bib` files
- `templates/`: paired LaTeX templates and template JSON configuration
- `output/`: generated `.tex`, `.pdf`, and LaTeX auxiliary files
- `tests/`: automated CLI and rendering tests

## Commands

Launch the desktop GUI:

```bash
python3 gui.py
```

Run the interactive prompt:

```bash
python3 cli.py
```

You can run the same commands either directly from the shell or inside the interactive prompt.

### `add`

Create a new BibTeX entry in a selected collection by answering prompts for the entry fields.

Example:

```bash
python3 cli.py add publications
```

### `list`

Display all entries in one collection in a readable summary format.

Example:

```bash
python3 cli.py list talks
```

### `lint`

Validate one collection or all collections, including missing required fields, malformed records, duplicate cite keys, and duplicate publication DOIs where present.

Examples:

```bash
python3 cli.py lint
python3 cli.py lint publications
```

### `show`

Display one entry identified by collection and cite key in raw BibTeX form.

Example:

```bash
python3 cli.py show talks johndoe_ibm_2026
```

### `edit`

Update one existing entry by setting or removing fields without manually editing the `.bib` file.

Examples:

```bash
python3 cli.py edit talks johndoe_ibm_2026 --set presentation_type=poster
python3 cli.py edit talks johndoe_ibm_2026 --set event_location="Chicago, IL" --remove venue
```

### `import-doi`

Fetch publication metadata from a DOI and create a publication entry. You may optionally provide a custom cite key.

Examples:

```bash
python3 cli.py import-doi publications 10.1038/nphys1170
python3 cli.py import-doi publications 10.1038/nphys1170 --key my_custom_key
```

### `import-bibtex`

Import one or more BibTeX entries into a collection from a file or from a raw BibTeX string.

Examples:

```bash
python3 cli.py import-bibtex publications --file path/to/paper.bib
python3 cli.py import-bibtex publications --string "@article{demo, title={Example}, author={Doe, John}, year={2024}}"
```

### `normalize`

Preview or apply conservative cleanup rules for one collection.

Examples:

```bash
python3 cli.py normalize talks --dry-run
python3 cli.py normalize talks --apply
```

### `render`

Generate a LaTeX CV from the configured BibTeX collections and template. You can optionally filter entries or request PDF compilation.

Examples:

```bash
python3 cli.py render
python3 cli.py render --output cv_preview
python3 cli.py render --min-year 2024 --keyword workflow
python3 cli.py render --compile
```

### Interactive mode helpers

When you run `python3 cli.py` with no arguments, the program starts interactive mode with the prompt `pyBibCV>`.

Special interactive commands:

- `help`: show the available commands
- `exit`: leave interactive mode
- `quit`: leave interactive mode

## Desktop GUI

The Tkinter desktop application reuses the same backend logic as the CLI. It is launched with:

```bash
python3 gui.py
```

The main window includes:

- a collection list
- an entry list for the selected collection
- an entry detail panel
- action buttons and menu items for add, edit, DOI import, BibTeX import, validation, normalization, and rendering

The GUI is intentionally practical rather than highly styled. It is designed to cover routine workflows without reimplementing business logic outside the shared backend modules.

## How rendering works

The `render` command reads the configured BibTeX files, then loads a matching template pair from `templates/`: a LaTeX skeleton such as `basic_cv.tex` and a JSON spec such as `basic_cv.json`. The JSON spec defines which sections appear, which BibTeX category feeds each section, how entries are formatted with field placeholders, and which list style each section uses. The generated `.tex` file is written to `output/`.

By default, the renderer uses the template named by `template_name` in `config.json`. You can still override that choice for a single run with `--template`.

## Template configuration

Each template JSON file can define:

- `document_title`: title inserted into the LaTeX document
- `sections`: ordered section definitions

Each section definition can define:

- `category`: BibTeX category name such as `publications`
- `list`: `itemize`, `enumerate`, or `reverse-enumerate`
- `format`: text pattern using placeholders like `<<author>>` or `<<title>>`

This keeps app-level configuration separate from template/style decisions.

## Optional PDF compilation

If you run `render --compile`, the program looks for one of these tools:

- `latexmk`
- `xelatex`
- `pdflatex`

If one is installed, it will be used to try to compile the generated `.tex` file into a PDF. If no LaTeX compiler is available, the command still succeeds in generating the `.tex` file and reports that PDF compilation was skipped.

## Generated files

Rendering writes files into `output/`, including:

- `cv.tex` or another name chosen with `--output`
- `cv.pdf` when compilation succeeds
- auxiliary LaTeX build files if a compiler creates them

## Tests

Run the automated tests with:

```bash
python3 -m unittest discover -s tests
```

The DOI success test uses a real network lookup and will skip automatically if network access is unavailable on the test machine.
