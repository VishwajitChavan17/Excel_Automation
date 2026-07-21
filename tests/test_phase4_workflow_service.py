"""
tests/test_phase4_workflow_service.py
========================================
Headless tests for workflow_service: individual step runners, chained
multi-step workflows, batch processing across many sources, and
save/load round-tripping. No Qt import anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.excel import workflow_service
from app.services.excel.models import WorkflowStep


def test_run_workflow_single_remove_duplicates_step():
    df = pd.DataFrame({"VIN": ["A1", "A1", "A2"], "Engine": ["E1", "E1", "E2"]})
    steps = [WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["VIN", "Engine"], "keep": "first"})]
    result_df, step_results = workflow_service.run_workflow(df, steps)
    assert len(result_df) == 2
    assert len(step_results) == 1
    assert step_results[0].success


def test_run_workflow_validate_step_does_not_mutate():
    df = pd.DataFrame({"ID": [1, None, 3]})
    steps = [WorkflowStep(step_type="validate", parameters={"rules": [{"rule_type": "required", "column": "ID"}]})]
    result_df, step_results = workflow_service.run_workflow(df, steps)
    assert len(result_df) == 3  # unchanged
    assert step_results[0].success is False  # 1 issue found -> step "fails" its own check
    assert "1 issue" in step_results[0].detail


def test_run_workflow_column_map_step():
    df = pd.DataFrame({"SignalName": ["S1"], "Unit": ["V"]})
    steps = [
        WorkflowStep(
            step_type="column_map",
            parameters={"mappings": [{"source_column": "SignalName", "destination_column": "Signal"}]},
        )
    ]
    result_df, step_results = workflow_service.run_workflow(df, steps)
    assert list(result_df.columns) == ["Signal"]
    assert step_results[0].success


def test_run_workflow_chained_steps():
    df = pd.DataFrame({"ID": [1, 1, 2], "Name": ["A", "A", "B"]})
    steps = [
        WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["ID"]}),
        WorkflowStep(
            step_type="column_map",
            parameters={"mappings": [{"source_column": "ID", "destination_column": "Identifier"}]},
        ),
    ]
    result_df, step_results = workflow_service.run_workflow(df, steps)
    assert len(result_df) == 2
    assert list(result_df.columns) == ["Identifier"]
    assert len(step_results) == 2


def test_run_workflow_requires_steps():
    df = pd.DataFrame({"A": [1]})
    with pytest.raises(ValueError):
        workflow_service.run_workflow(df, [])


def test_run_workflow_unknown_step_type_raises():
    df = pd.DataFrame({"A": [1]})
    with pytest.raises(ValueError):
        workflow_service.run_workflow(df, [WorkflowStep(step_type="not_a_real_step", parameters={})])


def test_run_workflow_step_failure_stops_chain_but_records_result():
    df = pd.DataFrame({"A": [1]})
    steps = [
        WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["NoSuchColumn"]}),
        WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["A"]}),
    ]
    result_df, step_results = workflow_service.run_workflow(df, steps)
    assert len(step_results) == 1  # second step never runs
    assert step_results[0].success is False


def test_run_workflow_batch_across_multiple_sources():
    sources = [
        ("file_a.xlsx", pd.DataFrame({"VIN": ["A1", "A1"], "Engine": ["E1", "E1"]})),
        ("file_b.xlsx", pd.DataFrame({"VIN": ["B1", "B2"], "Engine": ["E1", "E2"]})),
    ]
    steps = [WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["VIN", "Engine"]})]
    results = workflow_service.run_workflow_batch(sources, steps)

    assert len(results) == 2
    assert results[0].source_label == "file_a.xlsx"
    assert results[0].row_count_before == 2
    assert results[0].row_count_after == 1
    assert results[1].row_count_after == 2  # no duplicates in file_b


def test_run_workflow_batch_one_source_failing_does_not_stop_others():
    sources = [
        ("bad.xlsx", pd.DataFrame({"X": [1]})),
        ("good.xlsx", pd.DataFrame({"VIN": ["A1", "A1"], "Engine": ["E1", "E1"]})),
    ]
    steps = [WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["VIN", "Engine"]})]
    results = workflow_service.run_workflow_batch(sources, steps)

    assert len(results) == 2
    bad, good = results
    assert bad.source_label == "bad.xlsx"
    assert bad.row_count_after == 1  # step failed internally, stayed unchanged
    assert good.row_count_after == 1  # duplicate removed successfully


def test_save_and_load_workflow(tmp_path: Path):
    steps = [
        WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["ID"], "keep": "first"}, description="Dedup"),
        WorkflowStep(
            step_type="column_map",
            parameters={"mappings": [{"source_column": "ID", "destination_column": "Identifier"}]},
            description="Rename ID",
        ),
    ]
    path = workflow_service.save_workflow("My Workflow", steps, tmp_path)
    assert path.exists()

    name, loaded_steps = workflow_service.load_workflow(path)
    assert name == "My Workflow"
    assert len(loaded_steps) == 2
    assert loaded_steps[0].step_type == "remove_duplicates"
    assert loaded_steps[0].parameters["columns"] == ["ID"]


def test_list_workflows(tmp_path: Path):
    steps = [WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["ID"]})]
    workflow_service.save_workflow("Workflow One", steps, tmp_path)
    workflow_service.save_workflow("Workflow Two", steps, tmp_path)
    workflows = workflow_service.list_workflows(tmp_path)
    assert len(workflows) == 2


def test_list_workflows_missing_dir(tmp_path: Path):
    workflows = workflow_service.list_workflows(tmp_path / "nonexistent")
    assert workflows == []


def test_export_batch_report(tmp_path: Path):
    sources = [("a.xlsx", pd.DataFrame({"VIN": ["A1", "A1"], "Engine": ["E1", "E1"]}))]
    steps = [WorkflowStep(step_type="remove_duplicates", parameters={"columns": ["VIN", "Engine"]})]
    results = workflow_service.run_workflow_batch(sources, steps)
    out = workflow_service.export_batch_report(results, tmp_path / "batch_report.xlsx")
    assert out.exists()
    df = pd.read_excel(out)
    assert len(df) == 1
    assert df.iloc[0]["Status"] == "OK"
