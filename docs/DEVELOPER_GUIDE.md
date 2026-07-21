# Excel Automation Studio -- Developer Guide

## Architecture overview

```
ExcelAutomationStudio/
├── app/
│   ├── core/            # config, logging, paths, plugin framework, workbook_registry,
│   │                     # audit_log, session_manager, autosave_manager
│   ├── services/excel/  # pure business logic -- zero Qt imports, fully unit-testable
│   ├── ui/               # PySide6 views
│   │   ├── panels/       # dockable widgets: Project Explorer, Properties, Console
│   │   └── widgets/      # reusable widgets: ExcelPreviewWidget, FileSheetPicker,
│   │                     # PandasTableModel, Ribbon, background_task helper
│   ├── workers/          # QThread background workers, one per long-running operation
│   └── plugins/          # every feature -- see PLUGIN_GUIDE.md
├── tests/                 # pytest suite: pure-logic tests + headless Qt GUI tests
├── build.spec             # PyInstaller build spec
├── installer.iss          # Inno Setup installer script (Windows, compile separately)
└── main.py                 # entry point
```

### Layering rules (why the app is structured this way)

1. **`app/services/excel/*` has zero Qt imports.** Every business
   operation -- loading, profiling, duplicate detection, comparison,
   lookup, merge, validation, column mapping, workflow execution,
   reporting -- is a plain function operating on pandas DataFrames. This
   is what makes the 90+ pure-logic tests possible without a display, and
   what would let this logic be reused in a CLI or batch script with no
   GUI dependency at all.
2. **`app/workers/*` wraps each service call in a `QObject` with a
   `run()` method**, meant to be moved to a `QThread`. Workers only
   translate between the service layer and Qt signals -- they contain no
   business logic themselves.
3. **`app/plugins/*` is the UI layer for each tool.** A plugin widget
   builds its controls, wires them to a worker via
   `app/ui/widgets/background_task.py:start_worker()`, and renders
   results. Plugins read shared state via `PluginContext` (`config`,
   `registry`, `main_window`) rather than reaching into `MainWindow`
   directly, except through the small set of public methods `MainWindow`
   exposes intentionally (`open_plugin_tab`, `open_files_dialog`,
   `register_generated_report`, `apply_autosave_settings`, and the
   `plugin_manager` / `audit_log` properties).
4. **`WorkbookRegistry` is the single source of truth for loaded data.**
   Every sheet of every loaded file lives here (not just the active
   sheet), because Compare/Lookup/Duplicate Finder/Merge all need to pick
   *which* sheet of *which* file to operate on. It also owns the
   undo/redo history (`replace_sheet_data()` snapshots the prior
   DataFrame) and emits signals (`workbook_added`, `workbook_updated`,
   `history_changed`, `mutation_recorded`) that `MainWindow` and plugins
   subscribe to instead of polling.

### Two Qt/threading pitfalls this codebase has already hit (read before touching worker code)

1. **A `QObject` moved to a `QThread` must be kept referenced by the
   caller.** `moveToThread()` does not root the Python wrapper object
   against garbage collection. If nothing but the `QThread`'s internal
   C++ pointer references the worker, Python can (and, under GC
   pressure, will) collect it before the new thread invokes `run()`,
   silently dropping the job. Every plugin that starts a worker stores it
   on `self` (e.g. `self._active_worker = worker`) for exactly this
   reason -- see the docstring in `app/ui/widgets/background_task.py`.
2. **A PySide6 `Signal` declared with `dict` as an argument type fails to
   convert the payload at emit time** ("Cannot copy-convert ... (dict) to
   C++"), silently corrupting the result rather than raising somewhere
   obvious. Declare such signals as `Signal(object)` when carrying an
   arbitrary Python container. See `app/workers/workflow_worker.py`.
3. **Loguru sinks run synchronously on whatever thread calls
   `logger.*()`**, including background workers. A sink that touches a
   `QWidget` directly is undefined behavior. `ConsolePanel`'s sink only
   emits a Qt signal; the widget mutation happens in a connected slot on
   the GUI thread. See `app/ui/panels/console_panel.py`.

### PyInstaller and the plugin system

`PluginManager.discover_and_load()` finds plugins via
`pkgutil.iter_modules()` + `importlib.import_module()` -- there is no
static `import app.plugins.compare_tool` anywhere in the source.
PyInstaller's static analysis cannot see dynamic imports like this, so
`build.spec` explicitly re-collects every `app.plugins.*` module (using
the same `pkgutil` mechanism, at build time) and passes it as
`hiddenimports`. **Any new plugin file is picked up automatically** by
this mechanism with no spec changes required. This was verified by
actually running `pyinstaller build.spec` and confirming the built binary
loads all plugins with zero errors -- see `docs/PERFORMANCE.md` and the
spec file's own docstring for details.

## Building and testing

```bash
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run the full test suite (headless; QT_QPA_PLATFORM=offscreen needed
# because the suite mixes pure-logic and Qt GUI tests in one run)
QT_QPA_PLATFORM=offscreen pytest tests/ -v

# Run the app from source
python main.py

# Build the packaged EXE (produces dist/ExcelAutomationStudio[.exe])
pyinstaller build.spec --noconfirm

# Build the Windows installer (Windows only, after the EXE build above)
ISCC.exe installer.iss
```

## Coding standards

- **Type hints everywhere.** Every function signature in `app/services`,
  `app/workers`, and `app/core` is fully typed.
- **Docstrings explain *why*, not just *what*,** especially where a
  design decision isn't obvious (see the threading-pitfall docstrings
  above for the pattern to follow).
- **No business logic in `app/plugins/*` beyond wiring.** If you find
  yourself writing pandas operations directly in a plugin widget, that
  logic almost certainly belongs in `app/services/excel/` instead, where
  it can be unit-tested without Qt.
- **Every new service function gets a headless test** in the matching
  `tests/test_phaseN_services.py` file. Every new plugin gets a headless
  GUI smoke test in the matching `tests/test_phaseN_gui_smoke.py` file,
  following the existing pattern: build the plugin widget directly
  against a bare `WorkbookRegistry` (no `MainWindow` needed unless you're
  specifically testing `MainWindow` integration), drive its worker via
  `QApplication.processEvents()` in a polling loop, and mock any
  `QMessageBox`/`QFileDialog`/`QInputDialog` calls the flow triggers (see
  any existing GUI smoke test file for the pattern -- forgetting to mock
  a modal dialog is the single most common cause of a hanging test in
  this codebase).
- **Never overwrite the user's original file.** Every "apply" action in
  every tool mutates the in-memory registry copy only; writing to disk
  always happens via an explicit Export action to a new path.

## Extending the app

- **New tool** -- see `PLUGIN_GUIDE.md`.
- **New workflow step type** -- add a runner function to
  `app/services/excel/workflow_service.py`'s `_RUNNERS` dict and a
  corresponding UI branch in `app/plugins/workflow_recorder_tool.py`'s
  step builder.
- **New validation rule type** -- add a checker function to
  `app/services/excel/validation_service.py`'s `_CHECKERS` dict and add
  it to `RULE_TYPE_LABELS` in `app/plugins/validation_tool.py`.
- **New report format** -- add an export function to
  `app/services/excel/report_service.py` and wire it into
  `app/workers/report_worker.py`'s `exporters` dict.
