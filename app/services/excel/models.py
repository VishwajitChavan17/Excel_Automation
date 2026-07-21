"""
app.services.excel.models
==========================
Plain dataclasses describing a loaded workbook and its columns. These are
the shapes passed between the loader service, the workers, and the UI --
kept dependency-free (no pandas/polars types leak out) so the UI layer never
needs to know which engine loaded the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

EngineName = Literal["pandas", "polars"]


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    null_count: int
    null_pct: float
    unique_count: int
    unique_pct: float
    duplicate_pct: float
    example_values: list[Any] = field(default_factory=list)
    max_length: int | None = None
    min_length: int | None = None
    min_value: Any = None  # numeric columns only
    max_value: Any = None  # numeric columns only
    is_numeric: bool = False


@dataclass
class SheetInfo:
    name: str
    row_count: int
    column_count: int
    is_hidden: bool = False
    is_empty: bool = False


@dataclass
class WorkbookHandle:
    """Represents one loaded file, tracked in the Project Explorer."""

    file_path: Path
    display_name: str
    extension: str
    engine_used: EngineName
    sheets: list[SheetInfo]
    active_sheet: str
    row_count: int
    column_count: int
    memory_usage_bytes: int
    loaded_at: datetime
    file_size_bytes: int = 0
    last_modified: datetime | None = None
    duplicate_row_count: int = 0
    blank_cell_count: int = 0
    column_profiles: list[ColumnProfile] = field(default_factory=list)

    @property
    def memory_usage_mb(self) -> float:
        return round(self.memory_usage_bytes / (1024 * 1024), 3)

    @property
    def file_size_display(self) -> str:
        size = self.file_size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)


@dataclass
class DuplicateReport:
    columns_checked: list[str]
    total_rows: int
    duplicate_row_count: int
    duplicate_row_indices: list[int]
    keep_strategy: str  # "first" | "last" | "highest"


@dataclass
class CompareReport:
    key_columns: list[str]
    master_file: str
    second_file: str
    matched_count: int
    missing_in_second: int  # present in master, absent in second
    new_in_second: int  # present in second, absent in master
    modified_count: int
    output_path: Path | None = None


@dataclass
class LookupReport:
    master_file: str
    target_file: str
    match_column: str
    copy_columns: list[str]
    matched_count: int
    unmatched_count: int
    output_path: Path | None = None


@dataclass
class MergeReport:
    mode: str  # "union" | "inner" | "left" | "right" | "outer"
    key_columns: list[str] = field(default_factory=list)
    source_count: int = 0
    result_row_count: int = 0
    result_column_count: int = 0
    output_path: Path | None = None


@dataclass
class ConsolidationGroup:
    columns: tuple[str, ...]
    sources: list[tuple[str, str]]  # (file_label, sheet_name)


@dataclass
class ConsolidationReport:
    groups: list[ConsolidationGroup]
    chosen_group_index: int
    consolidated_row_count: int
    consolidated_source_count: int
    mismatched_source_count: int
    output_path: Path | None = None


@dataclass
class ValidationRule:
    rule_type: str  # required | unique | regex | dtype_numeric | dtype_date | no_negative | custom_expression
    column: str | None
    parameter: str | None = None  # regex pattern / custom pandas-eval expression
    description: str = ""


@dataclass
class ValidationIssue:
    row_index: int
    column: str
    rule_type: str
    message: str


@dataclass
class ValidationReport:
    total_rows: int
    rules_checked: list[ValidationRule]
    issues: list[ValidationIssue] = field(default_factory=list)
    output_path: Path | None = None

    @property
    def issue_count(self) -> int:
        return len(self.issues)


@dataclass
class ColumnMapping:
    source_column: str
    destination_column: str


@dataclass
class WorkflowStep:
    step_type: str  # "remove_duplicates" | "validate" | "column_map"
    parameters: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class WorkflowStepResult:
    step_type: str
    description: str
    success: bool
    detail: str = ""


@dataclass
class WorkflowRunResult:
    source_label: str
    row_count_before: int
    row_count_after: int
    step_results: list[WorkflowStepResult] = field(default_factory=list)
    error: str | None = None
