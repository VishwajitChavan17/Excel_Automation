# -*- mode: python ; coding: utf-8 -*-
"""
build.spec
===========
PyInstaller build spec for Excel Automation Studio.

Build with:
    pyinstaller build.spec --noconfirm

Produces a single-file, windowed (no console) executable at
dist/ExcelAutomationStudio(.exe on Windows).

--------------------------------------------------------------------------
IMPORTANT -- why plugin_modules is collected explicitly below
--------------------------------------------------------------------------
app/core/plugin_manager.py discovers plugins at RUNTIME via
pkgutil.iter_modules() + importlib.import_module() -- it never contains a
static `import app.plugins.compare_tool` statement anywhere in the source.
PyInstaller's dependency analysis only follows static imports, so without
help it will NOT bundle any of the plugin modules, and the packaged EXE
will start but show an empty ribbon with zero tools. This spec collects
every module under app/plugins/ at BUILD TIME (via the same pkgutil
mechanism the app itself uses at run time) and feeds it to Analysis() as
hiddenimports, so every plugin ships correctly. Any new file dropped into
app/plugins/ is automatically picked up here too, with no spec edits
required -- the collection logic mirrors PluginManager.discover_and_load().
"""

import pkgutil
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH)

# -- collect every app.plugins.* module (see docstring above) --------------
sys.path.insert(0, str(project_root))
import app.plugins as plugins_pkg  # noqa: E402

plugin_modules = [
    module_info.name
    for module_info in pkgutil.iter_modules(plugins_pkg.__path__, prefix=f"{plugins_pkg.__name__}.")
]
print(f"[build.spec] Bundling {len(plugin_modules)} plugin module(s): {plugin_modules}")

# -- other hidden imports that dynamic loading / optional backends need ----
hidden_imports = (
    plugin_modules
    + collect_submodules("openpyxl")
    + [
        "pandas._libs.tslibs.base",
        "polars",
        "pyarrow",
        "xlsxwriter",
        "matplotlib.backends.backend_pdf",
        "matplotlib.backends.backend_agg",
        "PySide6.QtSvg",
    ]
)

# -- data files: bundle default config, and let matplotlib find its own data
datas = [
    (str(project_root / "config" / "settings.default.yaml"), "config"),
    (str(project_root / "assets"), "assets"),
]
datas += collect_data_files("matplotlib")

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ExcelAutomationStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed app -- no console window, per spec requirement
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "icons" / "app_icon.ico"),
)
