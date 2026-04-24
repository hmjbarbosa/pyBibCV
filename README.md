# pyBibCV

`pyBibCV` is a Python command-line tool for managing CV data in BibTeX files and rendering that data into a basic LaTeX CV.

## Current project structure

- `cli.py`: command-line interface and interactive prompt
- `src/bibtex_ops.py`: BibTeX parsing, formatting, loading, and linting
- `src/import_ops.py`: DOI import and BibTeX import helpers
- `src/render_ops.py`: CV section grouping, filtering, LaTeX rendering, and optional PDF compilation
- `config.json`: app-level settings such as category file paths, required fields, the default template name, output settings, and author defaults
- `data/`: source `.bib` files
- `templates/`: paired LaTeX templates and template JSON configuration
- `output/`: generated `.tex`, `.pdf`, and LaTeX auxiliary files
- `tests/`: automated CLI and rendering tests

## Commands

Run the interactive prompt:

```bash
python3 cli.py
```

Inside the prompt, you can run commands like:

```text
add publications
list talks
lint
show talks barbosa_agu_2026
edit talks barbosa_agu_2026 --set presentation_type=poster
import-bibtex publications --string "@article{demo, title={Example}, author={Doe, John}, year={2024}}"
normalize talks --dry-run
render --output cv_preview
render --min-year 2024 --compile
```

Run commands directly:

```bash
python3 cli.py list publications
python3 cli.py lint
python3 cli.py show talks barbosa_agu_2026
python3 cli.py edit talks barbosa_agu_2026 --set event_location="Chicago, IL"
python3 cli.py import-doi publications 10.1038/nphys1170
python3 cli.py import-bibtex publications --file path/to/paper.bib
python3 cli.py normalize talks --apply
python3 cli.py render
python3 cli.py render --output cv_preview
python3 cli.py render --min-year 2024 --keyword workflow
python3 cli.py render --compile
```

## Milestone 3 commands

- `show <category> <cite_key>`: print one BibTeX entry in a readable raw form
- `edit <category> <cite_key> --set field=value --remove field`: update existing entries without opening the `.bib` file manually
- `import-doi <category> DOI [--key custom_key]`: fetch publication metadata over the network and create an entry
- `import-bibtex <category> --file path` or `--string "..."`: import one or more BibTeX entries
- `normalize <category> --dry-run` or `--apply`: preview or apply conservative cleanup rules

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
