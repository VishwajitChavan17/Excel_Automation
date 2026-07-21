# Excel Automation Studio -- Plugin Guide

Every feature in the ribbon -- Compare, Duplicate Finder, Merge, all of
them -- is a plugin. Adding a new tool requires **zero** changes to the
ribbon, the main window, or the plugin manager: drop a file in
`app/plugins/`, and it appears automatically on the correct ribbon tab.

## The three pieces of a plugin

1. **`PluginMetadata`** -- static, declarative description (id, display
   name, ribbon category, description, version).
2. **A `Plugin` subclass** -- the lifecycle object `PluginManager`
   discovers and loads. Its only required method is `create_widget()`.
3. **A `QWidget` subclass** -- the actual UI, built lazily the first time
   the user opens this tool's ribbon button.

## Minimal example

```python
# app/plugins/my_tool.py
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata


class MyToolWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Hello from My Tool"))


class MyToolPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="excel.my_tool",       # must be globally unique
        display_name="My Tool",           # shown on the ribbon button
        category=PluginCategory.EXCEL,    # controls which ribbon tab it appears on
        description="What this tool does.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return MyToolWidget(self.context, parent)
```

That's the whole integration. `PluginManager.discover_and_load()` finds
this file via `pkgutil.iter_modules()`, instantiates `MyToolPlugin`, and
the Ribbon reads `plugins_by_category()` to place a button under the
`Excel` tab automatically.

**Ribbon categories** (`app.core.plugin_base.PluginCategory`): `HOME`,
`IMPORT`, `EXCEL`, `COMPARE`, `MERGE`, `TRANSFORM`, `VALIDATION`,
`REPORTS`, `AUTOMATION`, `TEMPLATES`, `SETTINGS`, `ENGINEERING` (reserved
for future specialized tools -- DBC comparators, CAN matrix tools, etc.),
`OTHER`.

## What `self.context` gives you

`PluginContext`, available as `self.context` inside your `Plugin`
subclass (and typically passed straight to your widget's `__init__`):

| Field | Type | What it's for |
|---|---|---|
| `config` | `ConfigManager` | Read/write persisted settings (`config.get("app.theme")`, `config.set(...)`) |
| `registry` | `WorkbookRegistry` | Every loaded file/sheet -- see below |
| `main_window` | `MainWindow \| None` | Set *after* construction (plugins are instantiated before the window exists) -- see note below |

### Using the registry

```python
from app.ui.widgets.file_sheet_picker import FileSheetPicker

picker = FileSheetPicker(context.registry, label="File:")
df = picker.selected_dataframe()          # currently selected DataFrame, or None
key = picker.selected_file_key()          # registry key (== str(file_path))
sheet = picker.selected_sheet()
```

`FileSheetPicker` is the standard two-combo-box "pick a loaded file, then
pick one of its sheets" widget used by Compare, Lookup & Copy, Duplicate
Finder, Merge, and more. It stays live as files are loaded/closed via the
registry's `workbook_added`/`workbook_removed` signals -- use it instead
of hand-rolling file selection.

### Mutating data (with automatic Undo support)

```python
context.registry.replace_sheet_data(
    key, sheet_name, updated_df,
    description="Applied My Tool",   # shows in Project Explorer -> History
                                        # and is what Undo/Redo displays
)
```

This automatically snapshots the previous data onto the undo stack and
notifies every open preview tab for that file to refresh. Never mutate a
DataFrame you got from the registry in place -- always build a new one
and call `replace_sheet_data`.

### `main_window` is `None` during `__init__`

Plugins are instantiated once at startup, before `MainWindow` exists.
`PluginManager.attach_main_window()` fills in `context.main_window` right
after the window is built. If your widget's constructor needs it, guard
with `if self._context.main_window is not None:` -- by the time the user
can actually click a button in your widget, it's always set.

Useful `MainWindow` methods for plugins to call:

- `open_plugin_tab(plugin_id)` -- open another tool's tab (returns the
  widget, so you can pre-fill it -- see Compare's `preselect_master()`
  pattern used by the Project Explorer's "Compare With..." action).
- `open_files_dialog()` / `open_folder_dialog()` -- trigger the standard
  file-loading flow.
- `register_generated_report(path)` -- register a file you wrote with
  Project Explorer -> Reports and get a console notification for free.
- `apply_autosave_settings()` -- call after changing auto-save config so
  it takes effect immediately (see the Settings plugin).
- `plugin_manager` (property) -- the `PluginManager`, for building a UI
  like Settings -> Plugin Manager.
- `audit_log` (property) -- the persistent `AuditLog`, for a UI like
  Settings -> Audit Log.

## Adding a background-threaded operation

Business logic belongs in `app/services/excel/`, not in the plugin
widget -- see the Developer Guide's layering rules. The plugin's job is
just to wire a worker to that logic:

```python
# app/services/excel/my_service.py -- pure logic, no Qt, fully unit-testable
def do_the_thing(df: pd.DataFrame, param: str) -> tuple[pd.DataFrame, MyReport]:
    ...

# app/workers/my_worker.py
from PySide6.QtCore import QObject, Signal
from app.services.excel import my_service

class MyWorker(QObject):
    finished = Signal(object, object)   # use `object`, not `dict` -- see Developer Guide
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, df, param):
        super().__init__()
        self._df, self._param = df, param

    def run(self):
        try:
            self.progress.emit(20)
            result_df, report = my_service.do_the_thing(self._df, self._param)
            self.progress.emit(100)
            self.finished.emit(result_df, report)
        except Exception as exc:
            self.failed.emit(str(exc))
```

```python
# inside your plugin widget
from app.ui.widgets.background_task import start_worker
from app.workers.my_worker import MyWorker

def _on_run_clicked(self):
    worker = MyWorker(df, param)
    thread = start_worker(self, worker)
    self._active_thread = thread
    self._active_worker = worker  # MUST keep a reference -- see Developer Guide pitfall #1
    worker.progress.connect(self._progress_bar.setValue)
    worker.finished.connect(self._on_finished)   # bound method, not a lambda
    worker.failed.connect(self._on_failed)
    self._threads.append(thread)
    thread.start()

def _on_finished(self, result_df, report):
    thread = self._active_thread
    thread.quit()
    thread.wait()
    ...
```

## Testing your plugin

Two test files, following the existing pattern exactly:

```python
# tests/test_my_tool_service.py -- pure logic, no Qt
from app.services.excel import my_service

def test_do_the_thing():
    result_df, report = my_service.do_the_thing(sample_df, "x")
    assert ...
```

```python
# tests/test_my_tool_gui_smoke.py -- headless Qt, no MainWindow needed
import pytest
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])

def test_my_tool_widget(qapp, tmp_path):
    from app.core.config_manager import ConfigManager
    from app.core.plugin_base import PluginContext
    from app.core.workbook_registry import WorkbookRegistry
    from app.plugins.my_tool import MyToolWidget

    registry = WorkbookRegistry()
    # ... registry.add(handle, sheets) with a real loaded file ...
    ctx = PluginContext(config=ConfigManager(config_path=tmp_path / "s.yaml"), registry=registry)
    widget = MyToolWidget(ctx)
    widget._on_run_clicked()
    # poll app.processEvents() until the worker's result lands, then assert
```

**Common pitfall:** if your flow shows a `QMessageBox` or `QFileDialog`,
mock it in the test (`monkeypatch.setattr(QMessageBox, "information",
staticmethod(lambda *a, **k: QMessageBox.Ok))`) -- an unmocked modal
dialog under `QT_QPA_PLATFORM=offscreen` blocks the test forever with no
error message, which is the single most common cause of a hanging test
in this codebase's history.

## PyInstaller note

New plugin files are picked up automatically by `build.spec`'s dynamic
`app.plugins.*` collection -- no packaging changes needed. See the
Developer Guide's PyInstaller section for why this matters.
