# pyBibCV

`pyBibCV` is a Python command-line tool for managing CV data in BibTeX files and rendering that data into a basic LaTeX CV.

## Current project structure

- `cli.py`: command-line interface and interactive prompt
- `bibtex_ops.py`: BibTeX parsing, formatting, loading, and linting
- `render_ops.py`: CV section grouping, filtering, LaTeX rendering, and optional PDF compilation
- `config.json`: app-level settings such as category file paths, required fields, the default template name, output settings, and author defaults
- `data/`: source `.bib` files
- `templates/`: paired LaTeX templates and template JSON configuration
- `output/`: generated `.tex`, `.pdf`, and LaTeX auxiliary files
- `tests/`: automated tests for the rendering pipeline

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
render --output cv_preview
render --min-year 2024 --compile
```

Run commands directly:

```bash
python3 cli.py list publications
python3 cli.py lint
python3 cli.py render
python3 cli.py render --output cv_preview
python3 cli.py render --min-year 2024 --keyword workflow
python3 cli.py render --compile
```

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

Run the non-LaTeX rendering tests with:

```bash
python3 -m unittest discover -s tests
```
