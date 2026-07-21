# Excel Automation Studio

Enterprise-grade Windows desktop Excel automation suite for MTU / Rolls-Royce
Power Systems engineering teams. Built with PySide6, Pandas, Polars, and
OpenPyXL, packaged as a single EXE via PyInstaller.

> **Status: All 6 phases complete (v1.0.0).** Full architecture, every
> ribbon tool implemented and tested, enterprise hardening, PyInstaller
> packaging (built and verified), a Windows installer script, a complete
> documentation set, sample files, and measured performance at 500,000+
> rows. See [Roadmap](#roadmap) and `docs/PERFORMANCE.md` below.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python main.py
```

Run the full test suite (service-layer tests are display-free; GUI smoke
tests use Qt's offscreen platform so they also run without a display):

```bash
pytest tests/ -v
# or, explicitly headless:
QT_QPA_PLATFORM=offscreen pytest tests/ -v
```

## Documentation

- [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) -- every feature, how to use it
- [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) -- architecture, coding standards, known pitfalls
- [`docs/PLUGIN_GUIDE.md`](docs/PLUGIN_GUIDE.md) -- worked example for adding a new tool
- [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) -- measured numbers at 500,000+ rows
- [`samples/README.md`](samples/README.md) -- sample workbooks for trying every tool

## Packaging

```bash
# 1. Build the single-file EXE (produces dist/ExcelAutomationStudio[.exe])
pip install pyinstaller
pyinstaller build.spec --noconfirm

# 2. (Windows only) Build the installer, after step 1
#    Requires Inno Setup: https://jrsoftware.org/isinfo.php
ISCC.exe installer.iss
```

`build.spec` was actually built and run during development (see
`docs/PERFORMANCE.md` and the spec file's docstring) -- the resulting
binary starts, loads all 12 plugins with zero errors, and correctly
writes its config/logs next to the executable rather than into a
temporary unpack directory.

## What works today (Phase 2)

- **Home dashboard** -- real action cards (Load, Compare, Consolidate,
  Lookup & Copy, Merge, Data Cleaning) wired to actual tools, plus live
  Recent Files.
- **File loading** -- multi-file/folder open, full metadata (sheet count,
  row/column count, file size, last modified, load engine), dual pandas/
  Polars engine selection by file size.
- **Excel-like preview** -- click-to-sort, live search/filter across all
  columns, sheet tabs for multi-sheet workbooks, freeze-first-column,
  autofit columns, null/duplicate-row highlighting.
- **Properties panel** -- file identity, duplicate-row and blank-cell
  counts, per-column stats including numeric min/max.
- **Project Explorer** -- Loaded/Recent/Workflows/Templates/Reports/
  History/Favorites groups; right-click a loaded file for Preview, Rename,
  Reload, Close, Export, Duplicate, Compare With..., File Information.
- **Duplicate Finder** -- real multi-column duplicate detection, keep
  first/latest/highest-value strategies, in-place removal, Excel report
  export -- all on a background thread with progress.
- **Compare Excel** -- master/second file+sheet pickers, multi-key-column
  comparison, missing/new/modified row grids, highlighted `.xlsx` report
  export.
- **Lookup & Copy Values** -- master/target pickers, match column, copy
  columns, background VLOOKUP-style copy, apply in place or export.
- **Console** -- real log viewer: search, export, clear, color-coded
  levels, thread-safe (see note below).
- **Status bar** -- current file, active sheet, selected cell, zoom,
  row/column counts, background task progress.
- Every ribbon tab without a full implementation yet (Reports, Automation,
  Templates, Settings) shows a clear "planned, not broken" page listing
  what's coming and in which phase, instead of a blank placeholder.

## Phase 3 additions

- **Merge Files** -- union (stack rows across unlimited files, tagged with
  Source File) or SQL-style join (inner/left/right/outer) between two
  loaded files, all on a background thread with progress and `.xlsx`
  export.
- **Consolidate Files** -- select any number of loaded files/sheets;
  auto-detects which ones share an identical header signature, combines
  the largest matching group, and stamps every row with its source
  filename, source sheet, and import timestamp. Mismatched sources are
  reported, not silently dropped.
- **Validation Rules** -- build a rule set interactively (required, unique,
  regex pattern, numeric/date dtype, no-negative, or a custom pandas
  expression like `Qty > 0 and Price >= 0`), run in the background, review
  every issue in a sortable grid, export a highlighted report.
- **Column Mapper** -- map/rename a file's columns to a destination schema
  (optionally auto-suggested from a second reference file's headers via
  "Auto-map Identical Names"), apply in place or export, and save/load the
  mapping itself as a reusable JSON template under `templates/`.
- **Multi-Column Matching** -- Lookup & Copy Values now supports composite
  keys (e.g. `VIN + Engine Number`), matching the same capability already
  present in Compare and Duplicate Finder.

## Phase 4 additions

- **Undo/Redo** -- every in-place data mutation (remove duplicates, apply
  lookup, apply column mapping, apply a workflow batch run) is snapshotted
  onto a real undo stack. `Ctrl+Z` / `Ctrl+Y` (Edit menu) restore/reapply
  it, any already-open preview tab for the affected file refreshes
  automatically, and the Project Explorer's History group shows the live
  operation trail with timestamps.
- **Workflow Recorder** -- build an ordered, reusable sequence of steps
  (Remove Duplicates, Validate, Column Map) against a sample file's
  columns, save/load it as JSON under `workflows/`, then batch-run it
  against any number of already-loaded files at once -- one bad source
  doesn't stop the rest, and a per-source results grid shows exactly what
  happened. Results can be applied back to the loaded files (fully
  undoable) or exported as a batch report.
- **Report Generator** -- pick a loaded file, generate a summary report in
  any combination of Excel / CSV / HTML / PDF (the PDF includes a
  Matplotlib bar chart of null% by column). Also generates a standalone
  **Audit Report** from the session's operation history. Every generated
  file is registered with Project Explorer -> Reports automatically.
- **Template Manager** -- a real, working piece of the "Template Engine"
  requirement: browse every saved Column Mapping and Validation Rule Set
  template in one place, preview its JSON, and delete what you no longer
  need. Saving happens from the Column Mapper / Validation Rules tools
  themselves, where the data being templated already lives.

## Phase 5 additions

- **Persistent Audit Log** -- distinct from the in-memory Undo/Redo
  history (which is cleared on exit), every operation is now also written
  to a SQLite database (`database/audit.db`) that survives restarts.
  Searchable, exportable to Excel, viewable in Settings -> Audit Log.
- **Auto-Save & real crash recovery** -- on a configurable interval
  (default 120s), every loaded sheet's *current in-memory data* (not just
  the original file) is snapshotted to `autosave/`. If the app doesn't
  reach its own clean-shutdown code next time it starts -- a crash, a
  force-quit, an OS kill -- it detects that and offers to recover the
  actual unsaved edits, not just reopen the original files from scratch.
- **Session Restore** -- separately from autosave, the app remembers which
  files were open and offers to reopen them on a normal restart, governed
  by a toggle in Settings.
- **Settings / Plugin Manager** -- the last "coming soon" placeholder is
  now real: a Plugin Manager tab (every discovered plugin, load errors,
  enable/disable for next launch), Performance tuning (worker threads,
  large-file threshold), Auto-Save & Session configuration, and the Audit
  Log viewer described above.

Every ribbon category (Home, Import, Excel, Compare, Merge, Transform,
Validation, Reports, Automation, Templates, Settings) is now a complete,
working implementation.

## Phase 6 additions

- **PyInstaller packaging** -- `build.spec` produces a single-file,
  windowed EXE. This was actually built and run (not just written and
  hoped to work): the resulting binary starts, loads all 12 plugins with
  zero errors, and writes its config/logs next to the executable as
  designed. See the spec file's docstring for why plugin discovery needs
  special handling under PyInstaller (dynamic `pkgutil` imports aren't
  visible to static analysis) and how it's solved.
- **Windows installer** -- `installer.iss`, a complete Inno Setup script
  (Start Menu/Desktop shortcuts, uninstaller, persistent data folders)
  ready to compile on Windows.
- **Full documentation set** -- `docs/USER_MANUAL.md` (every feature),
  `docs/DEVELOPER_GUIDE.md` (architecture + pitfalls), `docs/PLUGIN_GUIDE.md`
  (worked example for adding a new tool), `docs/PERFORMANCE.md` (measured
  numbers, not estimates).
- **Sample files** -- `samples/`, six realistic workbooks, each verified
  to produce its documented result with the actual tool it's meant for.
- **Real performance validation at 500,000+ rows** -- see
  `docs/PERFORMANCE.md`. This benchmarking found and fixed two genuine
  bugs: a missing `pyarrow` dependency that would crash any large CSV/TSV
  load on a clean install, and an ~11x slowdown in Compare's modified-row
  diffing from a redundant per-cell Python loop, fixed by reusing
  already-vectorized masks. Both are covered by permanent regression
  tests in `tests/test_phase6_performance.py`.

## Architecture

```
ExcelAutomationStudio/
├── app/
│   ├── core/            # config, logging, paths, plugin framework, workbook_registry (no Qt/pandas deps in plugin_base)
│   ├── services/excel/  # pure business logic: loading, profiling, compare/duplicate/lookup (no Qt dependency -- testable headless)
│   ├── ui/               # PySide6 views: main window, panels, ribbon, theme, reusable widgets
│   │   ├── panels/       # dockable widgets: Project Explorer, Properties, Console
│   │   └── widgets/      # ExcelPreviewWidget, FileSheetPicker, PandasTableModel, Ribbon, background_task helper
│   ├── workers/          # QThread background workers (file load, compare, duplicate, lookup)
│   └── plugins/          # every feature lives here -- see "Adding a Plugin" below
├── config/                # settings.yaml (generated), settings.default.yaml (schema reference), session.json
├── database/              # audit.db (persistent SQLite audit trail)
├── logs/                  # rotating daily logs (app + errors), written next to the EXE
├── templates/             # saved column-mapping / validation-rule templates (validation/ subfolder)
├── workflows/             # saved multi-step Workflow Recorder JSON files
├── autosave/               # periodic in-memory-edit snapshots, used for crash recovery
├── exports/                # default output location for generated reports
├── tests/                  # pytest suite -- service-layer tests (no Qt) + offscreen GUI smoke tests
└── main.py                 # entry point: splash -> logging -> deps check -> config -> plugins -> window
```

### Design principles applied

- **Clean separation of concerns.** `app/services/excel/` has zero Qt imports
  -- it can be unit tested, reused in a CLI, or called from a batch script
  with no GUI dependency at all. All Compare/Duplicate/Lookup logic lives
  here and is independently tested in `tests/test_phase2_services.py`.
- **Plugin-based extensibility.** Every tool subclasses
  `app.core.plugin_base.Plugin`. `PluginManager` discovers them via
  filesystem scanning (`pkgutil.iter_modules`) -- **no manual registry to
  edit**. Drop a new file in `app/plugins/`, and it appears on the correct
  ribbon tab automatically.
- **Shared workbook registry.** `app.core.workbook_registry.WorkbookRegistry`
  is the single source of truth for "what's loaded" -- every sheet of every
  loaded file, not just the active one. MainWindow populates it; every
  plugin reads from it via `PluginContext.registry`, so plugins never need
  to reach into MainWindow directly and stay independently testable (see
  `tests/test_phase2_gui_smoke.py`, which builds plugin widgets against a
  bare `WorkbookRegistry` with no `MainWindow` at all).
- **Non-blocking I/O.** File loading, comparison, duplicate detection, and
  lookup/copy all run on a `QThread` via dedicated worker classes in
  `app/workers/`, so operating on large sheets never freezes the UI.
- **Thread-safety pitfalls, fixed and documented.** Two real bugs surfaced
  during development and are now guarded by regression tests:
  1. A `QObject` moved to a `QThread` via `moveToThread()` must also be
     kept referenced by the caller (e.g. `self._active_worker = worker`)
     for the thread's lifetime -- otherwise Python can garbage-collect it
     before the thread invokes `run()`, silently dropping the job. See the
     docstring in `app/ui/widgets/background_task.py`.
  2. Loguru sinks run synchronously on whatever thread calls `logger.*()`,
     including background workers. `ConsolePanel`'s sink only emits a Qt
     signal (thread-safe); the actual widget mutation happens in a
     connected slot on the GUI thread. See `app/ui/panels/console_panel.py`.
  3. A PySide6 `Signal` declared with `dict` as an argument type fails to
     convert the payload at emit time ("Cannot copy-convert ... (dict) to
     C++"), silently corrupting the result. Declare such signals as
     `Signal(object)` instead when carrying an arbitrary Python container.
     See `app/workers/workflow_worker.py`.
- **Frozen-EXE-safe paths.** `app/core/paths.py` distinguishes the
  PyInstaller onefile temp-unpack directory (`sys._MEIPASS`, read-only,
  wiped after exit) from the persistent, writable directory next to the
  EXE where logs/config/templates/exports actually live.
- **Config resilience.** `ConfigManager` deep-merges the on-disk YAML onto
  a hard-coded `DEFAULT_CONFIG`, so upgrading the app to a version with new
  settings never crashes on a missing key.

## Adding a Plugin

Copy `app/plugins/home_dashboard.py` or `app/plugins/duplicate_finder.py` as
a starting template:

```python
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata

class MyToolPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="excel.my_tool",       # must be globally unique
        display_name="My Tool",           # shown on the ribbon button
        category=PluginCategory.EXCEL,    # controls which ribbon tab it appears on
        description="What this tool does.",
    )

    def create_widget(self, parent=None):
        # self.context.registry gives access to every loaded workbook/sheet
        # self.context.main_window gives access to MainWindow helpers
        ...  # return a QWidget -- built lazily, only when the user opens the tool
```

Drop the file in `app/plugins/`. Nothing else needs to change -- no import
list to update, no ribbon wiring, no registry file.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Project architecture, UI shell, plugin framework, file loading | **Done** |
| 2 | Functional dashboard, interactive preview grid, Compare / Duplicate Finder / Lookup & Copy, richer Project Explorer & Properties panel, real console | **Done** |
| 3 | Merge/Consolidate, Validation Rules, Column Mapper, multi-column (composite-key) matching | **Done** |
| 4 | Workflow recorder, template engine, reporting (Excel/PDF/HTML), history/undo | **Done** |
| 5 | Enterprise hardening: audit logs, crash recovery, auto-save, session restore, plugin manager UI | **Done** |
| 6 | PyInstaller packaging, installer, full documentation set, performance tuning at 500k+ rows | **Done** |

All 6 phases are complete. This is v1.0.0.

## Testing

- `tests/test_phase1_core.py`, `tests/test_phase2_services.py`,
  `tests/test_phase3_services.py`, `tests/test_phase4_workflow_service.py`,
  `tests/test_phase4_report_service.py`, `tests/test_phase5_core.py`,
  `tests/test_phase6_performance.py` -- pure service/core-module tests
  (`ConfigManager`, `Plugin` lifecycle, every service module, plus
  audit_log/session_manager/autosave_manager and two performance
  regression tests -- see `docs/PERFORMANCE.md`). No Qt import; runs
  anywhere.
- `tests/test_phase2_gui_smoke.py`, `tests/test_phase3_gui_smoke.py`,
  `tests/test_phase4_gui_smoke.py`, `tests/test_phase4_history.py`,
  `tests/test_phase5_gui_smoke.py` -- headless GUI tests using Qt's
  `offscreen` platform. Build real plugin widgets (and, for crash-recovery
  and Settings tests, a real `MainWindow`) and drive them end-to-end.

All 137 tests pass headlessly; no display is required for CI. Run with
`QT_QPA_PLATFORM=offscreen pytest tests/ -v` (the env var is required
because the suite mixes pure-logic and GUI tests in one run).

