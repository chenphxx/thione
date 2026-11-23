# Repository Guidelines

thione is a Windows-only Python 3.10+ desktop toolbox built with tkinter/ttk. Changes should
remain small, follow the existing page and tool structure, and preserve unrelated work in the
working tree.

## Project Structure & Module Organization

- `main.py` initializes logging and the single-instance guard, then starts the Tk shell.
- `app/shell/` contains the main window, sidebar, and shared `ToolPage` base class.
- `app/tools/<tool>/` contains one feature per package, including `page.py`, `constants.py`, and
  supporting logic. Register pages in `app/tools/__init__.py`; registration order controls the
  sidebar.
- `app/browser/` holds the shared file browser components. `assets/images/` contains runtime
  images. `docs/` contains architecture and feature documentation in Simplified Chinese.
- `test/` and `test.py` are ignored local scratch resources, not an automated test suite.

## Build, Test, and Development Commands

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
python -m compileall -q app main.py
python -m PyInstaller --noconfirm --clean thione.spec
```

The last command creates `dist/thione.exe`. Runtime logs are written to both the terminal and
`%LOCALAPPDATA%\thione\logs\thione.log`.

## Coding Style & Naming Conventions

- Use 4-space indentation, double quotes, and the surrounding code's roughly 100-column style.
  No formatter or linter is configured.
- Use `snake_case` for modules and functions, `PascalCase` for classes, and `UPPER_CASE` for
  constants. Prefix internal helpers with `_`.
- Keep comments and docstrings consistent with existing Simplified Chinese `@param` /
  `@return` documentation.
- Only the main thread may touch tkinter objects. Return background results through the existing
  queue-and-`after` pattern.

## Testing Guidelines

There is no configured test framework, CI pipeline, or coverage threshold. Run the application
and manually exercise the changed tool plus startup and window switching. Check the log for
exceptions. If adding automated tests, place pure-logic tests under `tests/` and keep tkinter and
window creation out of them.

## Commit & Pull Request Guidelines

Use Conventional Commits with a short Chinese summary, for example
`fix: 修复长按 Ctrl 也会触发翻译的问题`. Common types are `feat`, `fix`, `docs`, `refactor`,
`style`, `perf`, `build`, and `chore`. Keep commits single-purpose.

Pull requests should explain the behavior change and motivation, link related issues, list
verification performed, and include screenshots for UI changes. Update `docs/` when behavior or
architecture changes, and update `CHANGELOG.md` only for user-visible changes.

## Security & Configuration

Never commit credentials or generated secrets. Translation credentials and preferences live in
`%APPDATA%\thione\config.ini` and `settings.ini`, outside the repository. Do not add dependencies
without first checking `requirements.txt` and `thione.spec`.
