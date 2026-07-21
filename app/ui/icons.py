"""Professional icon system using Unicode symbols.

Every icon in the application should resolve through this module so we can
swap to SVG icons later without touching every call site.
"""

# ── Core file / data symbols ─────────────────────────────────────────
FILE = "\u25C9"        # ◉
SHEET = "\u25A1"       # □
TABLE = "\u25A3"       # ▣
DATABASE = "\u25C8"    # ◈
REPORT = "\u25B6"      # ▶
WORKFLOW = "\u2699"    # ⚙
TEMPLATE = "\u2691"    # ⚑
HISTORY = "\u29D6"     # ⧖
FAVORITE = "\u2605"    # ★
RECENT = "\u29D7"      # ⧗
FOLDER = "\u25B8"      # ▸
HOME = "\u2302"        # ⌂

# ── Actions ──────────────────────────────────────────────────────────
COMPARE = "\u21C4"     # ⇄
MERGE = "\u229E"       # ⊞
VALIDATE = "\u2714"    # ✔
TRANSFORM = "\u21C6"   # ⇆
AUTOMATION = "\u26A1"  # ⚡
SEARCH = "\u2315"      # ⌕
EDIT = "\u270E"        # ✎
DELETE = "\u2716"      # ✖
CLOSE = "\u2715"       # ✕
ADD = "\u2795"         # ➕
REMOVE = "\u2796"      # ➖
EXPORT = "\u2B06"      # ⬆
IMPORT = "\u2B07"      # ⬇
PLAY = "\u25B6"        # ▶
PAUSE = "\u23F8"       # ⏸
STOP = "\u23F9"        # ⏹
SCHEDULE = "\u23F0"    # ⏰
SETTINGS = "\u2699"    # ⚙
MENU = "\u2630"        # ☰
PIN = "\u2716"         # (used for pin state)
UNDO = "\u21B6"        # ↶
REDO = "\u21B7"        # ↷
SAVE = "\u2714"        # ✔

# ── Status / Feedback ────────────────────────────────────────────────
SUCCESS = "\u2714"     # ✔
WARNING = "\u26A0"     # ⚠
ERROR = "\u2718"       # ✘
INFO = "\u2139"        # ℹ
PROGRESS = "\u29D6"    # ⧖

# ── Navigation ───────────────────────────────────────────────────────
BACK = "\u25C0"        # ◀
FORWARD = "\u25B6"     # ▶
UP = "\u25B2"          # ▲
DOWN = "\u25BC"        # ▼
EXPAND = "\u25BC"      # ▼
COLLAPSE = "\u25B6"    # ▶

# ── Category accent colors ───────────────────────────────────────────
CATEGORY_COLORS = {
    "Home": "#0078d4",
    "Import": "#0098a6",
    "Excel": "#107c10",
    "Compare": "#005a9e",
    "Merge": "#10893e",
    "Transform": "#5b2c8a",
    "Validation": "#d87b00",
    "Reports": "#881798",
    "Automation": "#00b7c3",
    "Templates": "#8764b8",
    "Settings": "#69797e",
    "Engineering": "#0078d4",
}

CATEGORY_ICONS = {
    "Home": HOME,
    "Import": IMPORT,
    "Excel": FILE,
    "Compare": COMPARE,
    "Merge": MERGE,
    "Transform": TRANSFORM,
    "Validation": VALIDATE,
    "Reports": REPORT,
    "Automation": AUTOMATION,
    "Templates": TEMPLATE,
    "Settings": SETTINGS,
    "Engineering": "\u2699",
}

# ── Ribbon group definitions ─────────────────────────────────────────
# Maps category -> {group_name: [plugin_id_prefixes]}
# Plugin IDs that match any prefix land in that group.
# Unknown plugins go to "Tools".
RIBBON_GROUPS: dict[str, dict[str, list[str]]] = {
    "Home": {
        "Project": ["home.new", "home.open", "home.save", "home.recent", "home.project"],
        "Import": ["import."],
        "Data Tools": ["compare.", "merge.", "lookup.", "validate.", "duplicate.", "consolidate."],
        "View": [],
    },
    "Import": {
        "Files": ["import.excel", "import.csv", "import.tsv", "import.folder"],
        "Connections": ["import.database", "import.sql", "import.sharepoint", "import.sqlite", "import.postgresql"],
        "Recent": [],
    },
    "Excel": {
        "Sheets": ["excel.sheet", "excel.rename", "excel.add", "excel.delete"],
        "Data": ["excel.filter", "excel.sort", "excel.split", "excel.merge"],
        "View": ["excel.preview", "excel.zoom", "excel.freeze"],
    },
    "Compare": {
        "Compare": ["compare.excel_compare", "compare.sheet", "compare.column", "compare.folder"],
        "Results": ["compare.diff_report", "compare.visual", "compare.highlight"],
        "Settings": ["compare.tolerance", "compare.settings", "compare.export"],
    },
    "Merge": {
        "Operations": ["merge.union", "merge.inner", "merge.left", "merge.right", "merge.append"],
        "Tools": ["merge.wizard", "merge.settings", "merge.export"],
    },
    "Transform": {
        "Clean": ["transform.trim", "transform.replace", "transform.regex", "transform.normalize"],
        "Columns": ["transform.split", "transform.merge_col", "transform.extract"],
        "Format": ["transform.uppercase", "transform.lowercase", "transform.format"],
    },
    "Validation": {
        "Find": ["validate.duplicate_finder", "validate.missing_values", "validate.business_rules"],
        "Rules": ["validate.format", "validate.column", "validate.date", "validate.email"],
        "Report": ["validate.data_quality_report", "validate.export"],
    },
    "Reports": {
        "Generate": ["reports.summary", "reports.charts", "reports.dashboard", "reports.statistics"],
        "Export": ["reports.export_excel", "reports.export_pdf", "reports.export_html"],
        "Analysis": ["reports.pivot", "reports.kpi", "reports.trend"],
    },
    "Automation": {
        "Control": ["automation.record", "automation.playback", "automation.pause", "automation.stop"],
        "Schedule": ["automation.schedule", "automation.batch", "automation.queue"],
        "Library": ["automation.workflows", "automation.templates", "automation.jobs"],
    },
    "Templates": {
        "Manage": ["templates.save", "templates.load", "templates.manage"],
        "Types": ["templates.column_mapping", "templates.validation", "templates.workflow"],
    },
    "Settings": {
        "Appearance": ["settings.theme", "settings.accent", "settings.language"],
        "System": ["settings.performance", "settings.plugins", "settings.updates", "settings.preferences"],
        "Shortcuts": ["settings.keyboard", "settings.about"],
    },
}

# ── Helper ───────────────────────────────────────────────────────────

def icon_for(plugin_id: str, default: str = "\u25CB") -> str:
    """Return a suitable icon for the given plugin_id."""
    mapping = {
        "compare": COMPARE,
        "merge": MERGE,
        "validate": VALIDATE,
        "duplicate": VALIDATE,
        "transform": TRANSFORM,
        "automation": AUTOMATION,
        "workflow": WORKFLOW,
        "template": TEMPLATE,
        "report": REPORT,
        "import": IMPORT,
        "export": EXPORT,
        "settings": SETTINGS,
        "preferences": SETTINGS,
        "theme": SETTINGS,
        "home": HOME,
        "excel": FILE,
        "csv": FILE,
        "folder": FOLDER,
        "database": DATABASE,
        "sql": DATABASE,
        "chart": REPORT,
        "dashboard": REPORT,
        "record": AUTOMATION,
        "playback": PLAY,
        "schedule": SCHEDULE,
        "batch": SCHEDULE,
        "lookup": SEARCH,
        "consolidate": MERGE,
        "kpi": REPORT,
        "pivot": TABLE,
    }
    for key, icon in mapping.items():
        if key in plugin_id.lower():
            return icon
    return default


def group_for_plugin(category: str, plugin_id: str) -> str:
    """Determine which ribbon group a plugin belongs to."""
    groups = RIBBON_GROUPS.get(category, {})
    for group_name, prefixes in groups.items():
        if not prefixes:
            continue
        for prefix in prefixes:
            if plugin_id.lower().startswith(prefix.lower()):
                return group_name
            if prefix.endswith(".") and plugin_id.lower().startswith(prefix.lower().rstrip(".")):
                return group_name
    if groups:
        return list(groups.keys())[0]
    return "Tools"
