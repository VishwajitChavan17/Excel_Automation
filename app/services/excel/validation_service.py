"""
app.services.excel.validation_service
========================================
Pure business logic for the Validation Rules tool: check a DataFrame
against a list of declarative rules and produce a flat list of issues
(row, column, rule, message) that the UI renders as a grid and can export
as an Excel report.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from loguru import logger

from app.services.excel.models import ValidationIssue, ValidationReport, ValidationRule

RULE_TYPES = (
    "required",
    "unique",
    "regex",
    "dtype_numeric",
    "dtype_date",
    "no_negative",
    "custom_expression",
)


def _check_required(df: pd.DataFrame, rule: ValidationRule) -> list[ValidationIssue]:
    mask = df[rule.column].isna()
    return [
        ValidationIssue(int(idx), rule.column, rule.rule_type, f"'{rule.column}' is required but blank")
        for idx in df.index[mask]
    ]


def _check_unique(df: pd.DataFrame, rule: ValidationRule) -> list[ValidationIssue]:
    mask = df.duplicated(subset=[rule.column], keep=False) & df[rule.column].notna()
    return [
        ValidationIssue(
            int(idx), rule.column, rule.rule_type, f"Duplicate value in '{rule.column}': {df.at[idx, rule.column]!r}"
        )
        for idx in df.index[mask]
    ]


def _check_regex(df: pd.DataFrame, rule: ValidationRule) -> list[ValidationIssue]:
    if not rule.parameter:
        raise ValueError(f"Regex rule on '{rule.column}' requires a pattern.")
    try:
        pattern = re.compile(rule.parameter)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern {rule.parameter!r}: {exc}") from exc

    values = df[rule.column].astype(str)
    non_null = df[rule.column].notna()
    matches = values.apply(lambda v: bool(pattern.match(v)))
    mask = non_null & ~matches
    return [
        ValidationIssue(
            int(idx),
            rule.column,
            rule.rule_type,
            f"'{rule.column}' value {df.at[idx, rule.column]!r} doesn't match pattern {rule.parameter!r}",
        )
        for idx in df.index[mask]
    ]


def _check_dtype_numeric(df: pd.DataFrame, rule: ValidationRule) -> list[ValidationIssue]:
    coerced = pd.to_numeric(df[rule.column], errors="coerce")
    mask = coerced.isna() & df[rule.column].notna()
    return [
        ValidationIssue(
            int(idx), rule.column, rule.rule_type, f"'{rule.column}' value {df.at[idx, rule.column]!r} is not numeric"
        )
        for idx in df.index[mask]
    ]


def _check_dtype_date(df: pd.DataFrame, rule: ValidationRule) -> list[ValidationIssue]:
    coerced = pd.to_datetime(df[rule.column], errors="coerce")
    mask = coerced.isna() & df[rule.column].notna()
    return [
        ValidationIssue(
            int(idx), rule.column, rule.rule_type, f"'{rule.column}' value {df.at[idx, rule.column]!r} is not a valid date"
        )
        for idx in df.index[mask]
    ]


def _check_no_negative(df: pd.DataFrame, rule: ValidationRule) -> list[ValidationIssue]:
    coerced = pd.to_numeric(df[rule.column], errors="coerce")
    mask = coerced < 0
    return [
        ValidationIssue(
            int(idx), rule.column, rule.rule_type, f"'{rule.column}' value {df.at[idx, rule.column]!r} is negative"
        )
        for idx in df.index[mask]
    ]


def _check_custom_expression(df: pd.DataFrame, rule: ValidationRule) -> list[ValidationIssue]:
    """`parameter` is a pandas boolean expression (as used by DataFrame.eval),
    e.g. "Quantity > 0 and Price >= 0". Rows where the expression evaluates
    False are reported as issues."""
    if not rule.parameter:
        raise ValueError("Custom expression rule requires an expression string.")
    try:
        satisfies = df.eval(rule.parameter)
    except Exception as exc:  # noqa: BLE001 - surface any eval error as a rule config problem
        raise ValueError(f"Invalid expression {rule.parameter!r}: {exc}") from exc

    if not hasattr(satisfies, "dtype") or satisfies.dtype != bool:
        raise ValueError(f"Expression {rule.parameter!r} must evaluate to a boolean per row.")

    mask = ~satisfies
    return [
        ValidationIssue(
            int(idx),
            rule.column or "(row)",
            rule.rule_type,
            f"Row fails rule: {rule.parameter}",
        )
        for idx in df.index[mask]
    ]


_CHECKERS = {
    "required": _check_required,
    "unique": _check_unique,
    "regex": _check_regex,
    "dtype_numeric": _check_dtype_numeric,
    "dtype_date": _check_dtype_date,
    "no_negative": _check_no_negative,
    "custom_expression": _check_custom_expression,
}


def run_validation(df: pd.DataFrame, rules: list[ValidationRule]) -> ValidationReport:
    if not rules:
        raise ValueError("At least one validation rule is required.")

    issues: list[ValidationIssue] = []
    for rule in rules:
        if rule.rule_type not in _CHECKERS:
            raise ValueError(f"Unknown rule type: {rule.rule_type!r}")
        if rule.rule_type != "custom_expression" and rule.column not in df.columns:
            raise ValueError(f"Column '{rule.column}' not found for rule '{rule.rule_type}'.")
        issues.extend(_CHECKERS[rule.rule_type](df, rule))

    report = ValidationReport(total_rows=len(df), rules_checked=list(rules), issues=issues)
    logger.info(
        "Validation complete: {} rule(s) checked, {} issue(s) found across {} row(s)",
        len(rules),
        len(issues),
        len(df),
    )
    return report


def export_validation_report(df: pd.DataFrame, report: ValidationReport, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    issues_df = pd.DataFrame(
        [
            {"Row": issue.row_index + 1, "Column": issue.column, "Rule": issue.rule_type, "Message": issue.message}
            for issue in report.issues
        ]
    )
    summary_df = pd.DataFrame(
        {
            "Metric": ["Total Rows", "Rules Checked", "Issues Found"],
            "Value": [report.total_rows, len(report.rules_checked), report.issue_count],
        }
    )

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        issues_df.to_excel(writer, sheet_name="Issues", index=False)
        if len(issues_df):
            workbook = writer.book
            red_fmt = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
            ws = writer.sheets["Issues"]
            ws.conditional_format(
                1, 0, len(issues_df), len(issues_df.columns) - 1, {"type": "no_errors", "format": red_fmt}
            )

    logger.info("Validation report written to {}", output_path)
    return output_path


# -- reusable rule-set templates ----------------------------------------


def save_validation_template(name: str, rules: list[ValidationRule], directory: str | Path) -> Path:
    import json

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip() or "validation"
    path = directory / f"{safe_name}.json"
    payload = [
        {"rule_type": r.rule_type, "column": r.column, "parameter": r.parameter, "description": r.description}
        for r in rules
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Saved validation template '{}' ({} rule(s)) to {}", name, len(rules), path)
    return path


def load_validation_template(path: str | Path) -> list[ValidationRule]:
    import json

    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        ValidationRule(
            rule_type=item["rule_type"],
            column=item.get("column"),
            parameter=item.get("parameter"),
            description=item.get("description", ""),
        )
        for item in data
    ]


def list_validation_templates(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))
