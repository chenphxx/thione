# Repository Guidelines

thione is a Windows-only desktop toolbox (Python 3.10+, tkinter/ttk) bundling file and text
utilities: image dedupe, batch rename, selection translate, radix conversion, port inspection,
audio conversion, and a serial/network assistant.

## Project Structure & Module Organization

```
main.py            entry point: single-instance guard, Tk root, mainloop
app/
  shell/           main window, sidebar, ToolPage base class (page.py)
  tools/           one subpackage per tool: dedupe, rename, translate, radix, port, convert, comm
  browser/         shared explorer-style file view (grid, preview, details, view bar)
  theme.py  settings.py  imaging.py  widgets.py  win32.py  constants.py
assets/images/     runtime icons (logo.ico)
docs/              architecture, dev guide, per-feature notes (Simplified Chinese)
thione.spec        PyInstaller spec    version_info.txt  exe version resource
```

Each tool lives in `app/tools/<name>/`, exports a `ToolPage` subclass from `page.py` with `key`,
`title`, `icon`, and `subtitle` class attributes, and registers it in `TOOL_PAGES`
(`app/tools/__init__.py`), where order is sidebar order. Per-tool constants go in that package's
`constants.py`. There is no test suite yet.

## Build, Test, and Development Commands

```powershell
py -3.15 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py                                        # run from source
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean thione.spec # build dist/thione.exe
```

Logs go to the terminal and `%LOCALAPPDATA%\thione\logs\thione.log`.

## Coding Style & Naming Conventions

- 4-space indent, double quotes, ~100-column soft limit. No formatter or linter is configured, so
  match surrounding code.
- `snake_case` modules and functions, `PascalCase` classes, `UPPER_CASE` module constants,
  `_underscore` for internal helpers.
- Docstrings and comments are Simplified Chinese in the `@param` / `@return` style — keep new code
  consistent.
- tkinter is not thread-safe: only the main thread touches Tk objects. Background threads post
  work via the queue + `after` pattern (`ShellWindow.post`). Keep non-UI logic importable without
  tkinter, as in `app/tools/radix/converter.py`.

## Testing Guidelines

No framework or CI is configured. Put tests for pure logic under `tests/` with `pytest`, free of
tkinter and window creation, and describe manual verification in the PR.

## Commit & Pull Request Guidelines

- Use Conventional Commits with a short Chinese summary, e.g.
  `fix: 修复长按ctrl也会触发翻译的问题`. Prefixes in use: `feat`, `fix`, `docs`, `chore`,
  `refactor`, `style`, `perf`, `build`.
- Keep each commit single-purpose and the subject under ~50 characters.
- PRs should state the change and motivation, link related issues, and include screenshots for UI
  changes. For releases, update `CHANGELOG.md` (newest `YYYY.M.D` heading first) and bump
  `__version__` in `app/__init__.py` together with `version_info.txt`.

## Security & Configuration

Never commit credentials. Translation keys are read from `%APPDATA%\thione\config.ini`, preferences
from `%APPDATA%\thione\settings.ini`; `.env` and `IAM_*-accessKeys.csv` are gitignored. Translation
providers implement `app/tools/translate/providers/provider.py` and convert language codes
internally, so business code only sees project codes (`zh`, `en`, ...).
