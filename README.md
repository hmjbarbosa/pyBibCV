# pyBibCV

`pyBibCV` is a Python command-line tool for managing CV data in BibTeX files and rendering that data into a basic LaTeX CV.

## Current project structure

- `cli.py`: command-line interface and interactive prompt
- `gui.py`: Tkinter desktop application entry point
- `src/bibtex_ops.py`: BibTeX parsing, formatting, loading, and linting
- `src/gui_controller.py`: thin controller layer shared by the Tkinter GUI and GUI-focused tests
- `src/import_ops.py`: DOI import and BibTeX import helpers
- `src/render_ops.py`: LaTeX-native `\CVList[...]` directive parsing, rendering, and optional PDF compilation
- `config.json`: app-level settings such as category file paths, required fields, the default template name, output settings, and author defaults
- `data/`: source `.bib` files
- `templates/`: LaTeX templates with embedded `\CVList[...]` directives
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

The `render` command reads the configured BibTeX files and then loads a LaTeX template from `templates/`. The template remains normal LaTeX, but it may contain special renderer directives of the form:

```latex
\CVList[collection=publications, sort=year_desc, list=enumerate, format="<<author>>, <<year>>: <<title>>"]
```

During rendering, the program:

1. reads the template text
2. finds each `\CVList[...]` directive
3. validates the directive options
4. loads the requested BibTeX collection
5. applies filtering, sorting, and limits
6. formats the selected entries into a LaTeX list
7. replaces the directive with the generated LaTeX

Ordinary LaTeX text outside those directives is left unchanged. The final `.tex` file is written to `output/`.

By default, the renderer uses the template named by `template_name` in `config.json`. You can still override that choice for a single run with `--template`.

## Template directives

Milestone 5 removed the old JSON template configuration approach. Templates are now LaTeX-only and use embedded directives.

The renderer currently supports exactly this directive:

- `\CVList[...]`

Supported directive options:

- `collection`
- `select`
- `sort`
- `limit`
- `list`
- `format`

Supported `select` forms:

- `select=all`
- `select=field(name,value)`
- `select=after(year)`
- multiple rules separated by `;`, for example `select=field(top5,yes);after(2020)`

Supported `sort` values:

- `year`
- `year_desc`
- `lastname`

Supported `list` values:

- `itemize`
- `enumerate`
- `etaremune`

Placeholders such as `<<author>>`, `<<year>>`, and `<<title>>` are replaced from BibTeX fields. Missing placeholders resolve to empty strings.

Current template examples:

- `templates/basic_cv.tex`: full CV-style template
- `templates/nsf_biosketch.tex`: more selective biosketch-style template

## Optional PDF compilation

If you run `render --compile`, the program looks for one of these tools:

- the configured preferred engine from `config.json`
- `latexmk`
- `xelatex`
- `pdflatex`

If one is installed, it will be used to try to compile the generated `.tex` file into a PDF. The default configuration prefers `xelatex` because it handles Unicode content better. If no LaTeX compiler is available, the command still succeeds in generating the `.tex` file and reports that PDF compilation was skipped.

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
