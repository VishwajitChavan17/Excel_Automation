"""
app.services.excel.report_service
====================================
Pure business logic for the Report Generator tool: build a summary report
(row/column counts, data-quality metrics, per-column stats) from an
already-loaded WorkbookHandle, and export it as Excel, CSV, HTML, or PDF
(the PDF includes a simple bar chart via Matplotlib, satisfying the
"Charts" requirement without adding a new dependency beyond what's already
in requirements.txt).

Also builds an "Audit Report" from a list of history entries (description +
timestamp), covering the audit-trail requirement.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from app.services.excel.models import WorkbookHandle


def build_summary_table(handle: WorkbookHandle) -> pd.DataFrame:
    """One row per column, matching what the Properties panel shows --
    the core of every summary/report export format below."""
    rows = []
    for profile in handle.column_profiles:
        rows.append(
            {
                "Column": profile.name,
                "Type": profile.dtype,
                "Null %": profile.null_pct,
                "Unique %": profile.unique_pct,
                "Duplicate %": profile.duplicate_pct,
                "Min": profile.min_value if profile.min_value is not None else "",
                "Max": profile.max_value if profile.max_value is not None else "",
                "Example Values": ", ".join(str(v) for v in profile.example_values[:3]),
            }
        )
    return pd.DataFrame(rows)


def build_file_metadata(handle: WorkbookHandle) -> dict[str, Any]:
    return {
        "File Name": handle.display_name,
        "Active Sheet": handle.active_sheet,
        "Sheet Count": handle.sheet_count,
        "Row Count": handle.row_count,
        "Column Count": handle.column_count,
        "File Size": handle.file_size_display,
        "Last Modified": handle.last_modified.strftime("%Y-%m-%d %H:%M") if handle.last_modified else "-",
        "Load Engine": handle.engine_used,
        "Duplicate Rows": handle.duplicate_row_count,
        "Blank Cells": handle.blank_cell_count,
    }


def export_summary_excel(handle: WorkbookHandle, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = build_file_metadata(handle)
    metadata_df = pd.DataFrame({"Property": list(metadata.keys()), "Value": list(metadata.values())})
    columns_df = build_summary_table(handle)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        metadata_df.to_excel(writer, sheet_name="Summary", index=False)
        columns_df.to_excel(writer, sheet_name="Column Statistics", index=False)

    logger.info("Summary Excel report written to {}", output_path)
    return output_path


def export_summary_csv(handle: WorkbookHandle, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_summary_table(handle).to_csv(output_path, index=False)
    logger.info("Summary CSV report written to {}", output_path)
    return output_path


def export_summary_html(handle: WorkbookHandle, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = build_file_metadata(handle)
    metadata_rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in metadata.items())
    columns_table_html = build_summary_table(handle).to_html(index=False, border=0, classes="cols")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Summary Report -- {handle.display_name}</title>
<style>
  body {{ font-family: Segoe UI, Arial, sans-serif; background:#0d1117; color:#c9d1d9; padding:24px; }}
  h1 {{ color:#e6edf3; }}
  table {{ border-collapse: collapse; margin-bottom: 24px; }}
  th, td {{ border: 1px solid #30363d; padding: 6px 12px; text-align: left; }}
  th {{ background:#161b22; }}
  table.cols {{ width: 100%; }}
</style>
</head>
<body>
  <h1>Summary Report: {handle.display_name}</h1>
  <table>{metadata_rows}</table>
  <h2>Column Statistics</h2>
  {columns_table_html}
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")
    logger.info("Summary HTML report written to {}", output_path)
    return output_path


def export_summary_pdf(handle: WorkbookHandle, output_path: str | Path) -> Path:
    """A simple, dependency-light PDF: one page with the file metadata and
    column-statistics table rendered via Matplotlib, plus a bar chart of
    null% per column (Matplotlib is already a project dependency, so this
    adds no new requirement)."""
    import matplotlib

    matplotlib.use("Agg")  # headless-safe backend, no display required
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = build_file_metadata(handle)
    columns_df = build_summary_table(handle)

    with PdfPages(output_path) as pdf:
        # Page 1: metadata + column stats table
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        ax.set_title(f"Summary Report: {handle.display_name}", fontsize=14, fontweight="bold", loc="left")

        meta_text = "\n".join(f"{k}: {v}" for k, v in metadata.items())
        ax.text(0.0, 0.97, meta_text, transform=ax.transAxes, fontsize=9, va="top", family="monospace")

        if not columns_df.empty:
            table_data = columns_df.head(25).values.tolist()  # cap rows so the table stays legible
            table = ax.table(
                cellText=table_data,
                colLabels=list(columns_df.columns),
                loc="lower center",
                cellLoc="left",
                bbox=[0.0, 0.0, 1.0, 0.55],
            )
            table.auto_set_font_size(False)
            table.set_fontsize(6)
        pdf.savefig(fig)
        plt.close(fig)

        # Page 2: null% bar chart, if there's anything to show
        if not columns_df.empty:
            fig2, ax2 = plt.subplots(figsize=(11, 8.5))
            ax2.bar(columns_df["Column"], columns_df["Null %"])
            ax2.set_ylabel("Null %")
            ax2.set_title(f"Null Percentage by Column -- {handle.display_name}")
            ax2.tick_params(axis="x", rotation=75)
            fig2.tight_layout()
            pdf.savefig(fig2)
            plt.close(fig2)

    logger.info("Summary PDF report written to {}", output_path)
    return output_path


# -- audit report (from history entries) -------------------------------------


def export_audit_report(entries: list[Any], output_path: str | Path) -> Path:
    """`entries` is a list of objects exposing .description and .timestamp
    (WorkbookRegistry.HistoryEntry). Exports the operation audit trail."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "Timestamp": [e.timestamp.strftime("%Y-%m-%d %H:%M:%S") for e in entries],
            "File": [getattr(e, "file_key", "") for e in entries],
            "Sheet": [getattr(e, "sheet_name", "") for e in entries],
            "Operation": [e.description for e in entries],
        }
    )
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Audit Trail", index=False)

    logger.info("Audit report written to {} ({} entries)", output_path, len(entries))
    return output_path
