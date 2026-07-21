# Excel Automation Studio -- User Manual

Version 1.0.0 | Rolls-Royce Power Systems (MTU) -- Internal Engineering Tools

## Contents

1. [Getting Started](#getting-started)
2. [The Workspace](#the-workspace)
3. [Loading Files](#loading-files)
4. [The Preview Grid](#the-preview-grid)
5. [Home Dashboard](#home-dashboard)
6. [Duplicate Finder](#duplicate-finder)
7. [Compare Excel](#compare-excel)
8. [Lookup & Copy Values](#lookup--copy-values)
9. [Merge & Consolidate](#merge--consolidate)
10. [Column Mapper](#column-mapper)
11. [Validation Rules](#validation-rules)
12. [Workflow Recorder & Batch Processing](#workflow-recorder--batch-processing)
13. [Report Generator](#report-generator)
14. [Template Manager](#template-manager)
15. [Undo / Redo and History](#undo--redo-and-history)
16. [Project Explorer](#project-explorer)
17. [Console & Notifications](#console--notifications)
18. [Settings](#settings)
19. [Auto-Save, Crash Recovery & Session Restore](#auto-save-crash-recovery--session-restore)
20. [Troubleshooting](#troubleshooting)

---

## Getting Started

Launch `ExcelAutomationStudio.exe`. A splash screen walks through startup
(dependency check, configuration, plugin discovery) and the main window
opens on the **Welcome** tab.

The window is organized like familiar Office/Power BI-style tools:

- **Ribbon** (top) -- one tab per tool category: Home, Import, Excel,
  Compare, Merge, Transform, Validation, Reports, Automation, Templates,
  Settings.
- **Project Explorer** (left) -- every loaded file, recent files, saved
  workflows, saved templates, generated reports, and operation history.
- **Center Workspace** -- every loaded file and every tool you open gets
  its own closable tab.
- **Properties** (right) -- details for whichever file/sheet is active.
- **Console / Notifications** (bottom) -- a live, searchable log of
  everything the app does, plus toast-style notifications.
- **Status bar** (very bottom) -- current file, sheet, selected cell,
  zoom, row/column counts, and background task progress.

## The Workspace

Every tool you open (Compare, Duplicate Finder, Workflow Recorder, ...)
appears as a new tab next to your open files. Tabs are closable and
reorderable. Opening the same tool again creates a fresh tab -- you can
have multiple Compare sessions open side by side.

## Loading Files

**File > Open File(s)...** (`Ctrl+O`), **File > Open Folder...**, or the
**Import** ribbon tab. Supported formats: `.xlsx .xlsm .xls .csv .tsv
.ods`. Loading runs on a background thread with a progress bar, so the UI
never freezes -- even for large files.

Loaded files appear under **Project Explorer -> Loaded Excel Files**,
showing sheet count, row/column count, size, and last-modified date on
hover. Double-click to open (or re-focus) its preview tab.

**Large files:** CSV/TSV files above 100,000 rows automatically switch
from pandas to Polars for parsing (configurable in Settings -> Performance),
which is dramatically faster at scale. See `PERFORMANCE.md` for measured
numbers up to 500,000 rows.

### Right-click a loaded file for:

| Action | What it does |
|---|---|
| Preview | Opens/focuses its tab |
| Rename | Changes its display name (cosmetic only) |
| Reload | Re-reads the file from disk, discarding in-memory edits |
| Close | Removes it from the Studio (never touches the file on disk) |
| Export | Saves the current sheet to a new `.xlsx` |
| Duplicate | Opens a second, independent preview tab of the same data |
| Compare With... | Opens Compare Excel with this file pre-selected as Master |
| File Information | Shows full metadata in a dialog |

## The Preview Grid

Every loaded file opens in an Excel-like grid:

- **Sort** -- click any column header.
- **Search / filter** -- the search box filters across every column live.
- **Sheet tabs** -- multi-sheet workbooks show a tab strip; switching
  sheets re-profiles instantly (no reload).
- **Freeze First Column** -- checkbox, for wide sheets with a key column.
- **Autofit Columns** -- button, resizes all columns to fit content.
- **Highlighting** -- blank cells and (where applicable) duplicate rows
  are tinted so problems are visible at a glance.

## Home Dashboard

Large action cards jump straight into the most common workflows (Load,
Compare, Consolidate, Lookup & Copy, Merge, Data Cleaning), plus a live
list of recently loaded files.

## Duplicate Finder

*Ribbon: Excel*

1. Pick a loaded file and sheet.
2. Select one or more columns to check (composite keys supported, e.g.
   `VIN` + `Engine Number`).
3. Choose a keep strategy: **First Occurrence**, **Latest Occurrence**, or
   **Highest Value** (ranks by the first other numeric column found).
4. **Find Duplicates** -- runs in the background; duplicate rows are
   highlighted directly in the embedded preview.
5. **Remove Duplicates** -- removes them in memory (undoable, `Ctrl+Z`)
   and updates the loaded file everywhere it's used in the Studio.
6. **Export Report** -- writes an Excel report of exactly which rows were
   flagged.

## Compare Excel

*Ribbon: Compare*

1. Pick a **Master** file/sheet and a **Second** file/sheet.
2. Select one or more shared key columns (composite keys supported).
3. Optionally check **Ignore Case** / **Ignore Spaces**.
4. **Compare** -- runs in the background. Results appear in three grids:
   **Missing In Second**, **New In Second**, **Modified**.
5. **Generate Comparison Report (.xlsx)** -- a color-coded Excel report
   (red/green/yellow sheets) plus a Summary sheet.

## Lookup & Copy Values

*Ribbon: Transform*

The VLOOKUP-replacement workflow: no formulas required.

1. Pick a **Master** (authoritative values) and a **Target** (receives
   values) file/sheet.
2. Select one or more **Match Column(s)** (composite-key matching
   supported -- select more than one for e.g. `VIN + Engine Number`).
3. Select one or more **Column(s) to Copy** from the master.
4. **Copy Matching Values** -- runs in the background; preview shows the
   updated target.
5. **Apply to Loaded Target** (in-memory, undoable) or **Export Updated
   Workbook** (new file).

## Merge & Consolidate

*Ribbon: Merge* -- two tabs:

**Merge Files** -- union (stack rows, tagged with Source File) or
SQL-style join (Inner / Left / Right / Outer) of exactly two files.

**Consolidate Files** -- select any number of loaded files/sheets. The
tool auto-detects which ones share an identical header signature,
combines the largest matching group, and stamps every row with its
source filename, sheet, and import timestamp. Mismatched sources are
listed, not silently dropped.

## Column Mapper

*Ribbon: Transform*

Rename/select a file's columns to a destination schema:

1. Pick a **Source** file/sheet.
2. Optionally pick a **Reference Schema** file whose column names should
   be used as auto-map targets.
3. **Auto-map Identical Names**, or build rows manually (source column +
   destination name).
4. **Apply Mapping** to preview the result; apply in place or export.
5. **Save Mapping Template...** to reuse this exact mapping later --
   browse/manage saved templates in **Templates -> Template Manager**.

## Validation Rules

*Ribbon: Validation*

Build a rule set against a loaded sheet:

- **Required** (not blank), **Unique** (no duplicates), **Regex** pattern
  match, **Must Be Numeric**, **Must Be a Valid Date**, **No Negative
  Values**, or a **Custom Expression** (any pandas boolean expression,
  e.g. `Qty > 0 and Price >= 0`).

Add as many rules as needed, **Run Validation**, and review every issue
(row, column, rule, message) in a sortable grid. **Export Validation
Report** writes a highlighted Excel report. **Save Rule Set...** stores
the whole rule list as a reusable template.

## Workflow Recorder & Batch Processing

*Ribbon: Automation*

Build a reusable, ordered sequence of steps -- **Remove Duplicates**,
**Validate**, **Column Map** -- against a sample file's columns, then run
that exact sequence against any number of already-loaded files at once.

1. Pick a **Sample File** so column names populate the step builder.
2. **Add Step** for each operation, in the order they should run.
3. **Save Workflow...** to reuse it later, or **Load** a saved one.
4. Select target files (checkable list of every loaded file/sheet).
5. **Run Workflow on Selected Files** -- one bad source doesn't stop the
   rest; a per-source results grid shows exactly what happened to each.
6. **Apply Results to Loaded Files** (undoable) or **Export Batch Report**.

## Report Generator

*Ribbon: Reports*

Pick a loaded file and any combination of **Excel / CSV / HTML / PDF**
(the PDF includes a null-percentage bar chart). Generated files are
registered under **Project Explorer -> Reports** automatically.

**Generate Audit Report** exports the session's full operation history
(everything logged in the persistent audit log) as an Excel file.

## Template Manager

*Ribbon: Templates*

Browse every saved Column Mapping and Validation Rule Set template in one
place, preview its contents, and delete what you no longer need. (Saving
happens from the Column Mapper and Validation Rules tools themselves.)

## Undo / Redo and History

Every in-place edit -- removing duplicates, applying a lookup, applying a
column mapping, applying a workflow batch run -- is undoable:

- **Edit menu > Undo** (`Ctrl+Z`) / **Redo** (`Ctrl+Y`).
- Any already-open preview tab for the affected file refreshes
  automatically.
- **Project Explorer -> History** shows the live, timestamped trail of
  every undoable operation this session.

This is separate from the **persistent Audit Log** (Settings -> Audit
Log), which survives restarts and records every load and every operation,
not just the ones currently on the undo stack.

## Project Explorer

Seven groups: **Loaded Excel Files**, **Recent Files**, **Saved
Workflows**, **Templates**, **Reports**, **History**, **Favorites**.
Everything the app generates (reports, workflows, templates) is
registered here automatically.

## Console & Notifications

**Console** tab: every log message the app produces, live, color-coded by
level (DEBUG/INFO/SUCCESS/WARNING/ERROR). Search, export to a text file,
or clear.

**Notifications** tab: a running list of toast-style events (file loaded,
report generated, errors) with timestamps.

## Settings

*Ribbon: Settings* -- four tabs:

- **Plugin Manager** -- every discovered tool, its ID/category/version,
  and any load errors. Uncheck a plugin to disable it (takes effect on
  next launch).
- **Performance** -- large-file row threshold (when Polars kicks in),
  max background worker threads, whether to use Polars automatically.
- **Auto-Save & Session** -- enable/disable periodic auto-save and its
  interval, whether to offer session restore on startup, and a button to
  clear autosave data immediately.
- **Audit Log** -- search, export, or clear the persistent SQLite audit
  trail described above.

## Auto-Save, Crash Recovery & Session Restore

Two related but distinct safety nets:

- **Session Restore**: on a normal restart, the app remembers which files
  were open and offers to reopen them (governed by a Settings toggle).
  This reopens the *original files*, not necessarily your latest edits.
- **Auto-Save / Crash Recovery**: on a configurable interval (default
  120s), every loaded sheet's *current in-memory data* -- including
  unsaved edits -- is snapshotted to disk. If the app doesn't reach its
  own clean-shutdown code next time it starts (a crash, a force-quit, an
  OS kill), it detects that and offers to recover the actual unsaved
  work, not just reopen the original files from scratch.

The Studio **never overwrites your original files**. Every destructive
action (removing duplicates, applying a workflow) only ever changes the
in-memory copy; saving to disk always happens via an explicit Export to a
new file.

## Troubleshooting

- **A tool's ribbon button does nothing / shows an error dialog** --
  check the Console tab for the underlying exception, and the daily log
  file under `logs/`.
- **"Missing Dependencies" on startup** -- run
  `pip install -r requirements.txt` in the same Python environment used
  to launch the app.
- **A plugin failed to load** -- check Settings -> Plugin Manager -> Load
  Errors for the exact module and exception.
- **Need to report a bug** -- Console -> Export Logs, attach the exported
  `.txt` file along with steps to reproduce.
