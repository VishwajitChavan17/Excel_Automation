"""
app.services.excel.workflow_service
======================================
Pure business logic for the Workflow Recorder / batch-processing tool.

A Workflow is an ordered list of WorkflowStep objects, each one a
declarative reference to an existing service (Duplicate Finder, Validation,
Column Mapper) plus its parameters -- reusing the exact same functions
already covered by tests in test_phase2_services.py / test_phase3_services.py
rather than re-implementing that logic. Running a workflow against a
DataFrame applies every step in order; running it against many (label, df)
sources applies the whole chain to each one independently, which is what
satisfies "run the same workflow on 100+ files automatically".

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from loguru import logger

from app.services.excel import duplicate_service, validation_service
from app.services.excel.column_mapper_service import apply_mapping
from app.services.excel.models import ColumnMapping, ValidationRule, WorkflowRunResult, WorkflowStep, WorkflowStepResult

STEP_TYPES = ("remove_duplicates", "validate", "column_map")


def _run_remove_duplicates(df: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, WorkflowStepResult]:
    columns = params.get("columns") or []
    keep = params.get("keep", "first")
    if not columns:
        raise ValueError("remove_duplicates step requires 'columns'.")
    before = len(df)
    result = duplicate_service.remove_duplicates(df, columns, keep=keep)
    removed = before - len(result)
    return result, WorkflowStepResult(
        step_type="remove_duplicates",
        description=f"Remove duplicates on {columns} (keep={keep})",
        success=True,
        detail=f"Removed {removed} row(s)",
    )


def _run_validate(df: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, WorkflowStepResult]:
    rules_raw = params.get("rules") or []
    rules = [ValidationRule(**r) if isinstance(r, dict) else r for r in rules_raw]
    if not rules:
        raise ValueError("validate step requires 'rules'.")
    report = validation_service.run_validation(df, rules)
    # Validation doesn't mutate the data -- it only reports issues.
    return df, WorkflowStepResult(
        step_type="validate",
        description=f"Validate against {len(rules)} rule(s)",
        success=report.issue_count == 0,
        detail=f"{report.issue_count} issue(s) found",
    )


def _run_column_map(df: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, WorkflowStepResult]:
    mappings_raw = params.get("mappings") or []
    mappings = [ColumnMapping(**m) if isinstance(m, dict) else m for m in mappings_raw]
    keep_unmapped = params.get("keep_unmapped", False)
    if not mappings:
        raise ValueError("column_map step requires 'mappings'.")
    result = apply_mapping(df, mappings, keep_unmapped=keep_unmapped)
    return result, WorkflowStepResult(
        step_type="column_map",
        description=f"Map {len(mappings)} column(s)",
        success=True,
        detail=f"Result has {result.shape[1]} column(s)",
    )


_RUNNERS = {
    "remove_duplicates": _run_remove_duplicates,
    "validate": _run_validate,
    "column_map": _run_column_map,
}


def run_workflow(df: pd.DataFrame, steps: list[WorkflowStep]) -> tuple[pd.DataFrame, list[WorkflowStepResult]]:
    """Apply every step in `steps`, in order, to `df`. A step that raises
    is recorded as a failed WorkflowStepResult and processing stops for
    this source (subsequent sources in a batch run are unaffected)."""
    if not steps:
        raise ValueError("A workflow requires at least one step.")

    current = df
    results: list[WorkflowStepResult] = []
    for step in steps:
        if step.step_type not in _RUNNERS:
            raise ValueError(f"Unknown workflow step type: {step.step_type!r}")
        try:
            current, result = _RUNNERS[step.step_type](current, step.parameters)
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - report and stop this source's chain
            results.append(
                WorkflowStepResult(
                    step_type=step.step_type, description=step.description, success=False, detail=str(exc)
                )
            )
            logger.warning("Workflow step '{}' failed: {}", step.step_type, exc)
            break
    return current, results


def run_workflow_batch(
    sources: list[tuple[str, pd.DataFrame]], steps: list[WorkflowStep]
) -> list[WorkflowRunResult]:
    """Run the same workflow independently against every (label, df) source
    -- the "run on 100+ files automatically" batch-processing workflow.
    One source failing does not stop the others."""
    results = []
    for label, df in sources:
        try:
            result_df, step_results = run_workflow(df, steps)
            results.append(
                WorkflowRunResult(
                    source_label=label,
                    row_count_before=len(df),
                    row_count_after=len(result_df),
                    step_results=step_results,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Workflow batch run failed for source '{}'", label)
            results.append(
                WorkflowRunResult(source_label=label, row_count_before=len(df), row_count_after=len(df), error=str(exc))
            )
    logger.info("Workflow batch run complete: {} source(s) processed", len(sources))
    return results


# -- save / load ------------------------------------------------------------


def save_workflow(name: str, steps: list[WorkflowStep], directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip() or "workflow"
    path = directory / f"{safe_name}.json"
    payload = {
        "name": name,
        "steps": [
            {"step_type": s.step_type, "parameters": s.parameters, "description": s.description} for s in steps
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Saved workflow '{}' ({} step(s)) to {}", name, len(steps), path)
    return path


def load_workflow(path: str | Path) -> tuple[str, list[WorkflowStep]]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    steps = [
        WorkflowStep(step_type=s["step_type"], parameters=s.get("parameters", {}), description=s.get("description", ""))
        for s in data["steps"]
    ]
    return data.get("name", path.stem), steps


def list_workflows(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def export_batch_report(results: list[WorkflowRunResult], output_path: str | Path) -> Path:
    """Write one summary Excel report covering every source processed in a
    batch run -- satisfies the "audit report" requirement for workflow runs."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for result in results:
        rows.append(
            {
                "Source": result.source_label,
                "Rows Before": result.row_count_before,
                "Rows After": result.row_count_after,
                "Status": "Error" if result.error else "OK",
                "Detail": result.error or "; ".join(f"{s.step_type}: {s.detail}" for s in result.step_results),
            }
        )
    summary_df = pd.DataFrame(rows)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        summary_df.to_excel(writer, sheet_name="Batch Run Report", index=False)

    logger.info("Workflow batch report written to {}", output_path)
    return output_path
