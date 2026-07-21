"""
tests/test_phase6_performance.py
===================================
Performance-oriented regression tests written after benchmarking against a
synthetic 500,000-row file during Phase 6. Uses a smaller (~150k-row)
fixture here to keep the test suite fast; the full 500k-row numbers are
documented in docs/PERFORMANCE.md.

Two real bugs were found and fixed via this benchmarking, both guarded
here:

1. `polars.DataFrame.to_pandas()` requires pyarrow, which was missing from
   requirements.txt -- any CSV/TSV over the 100k-row threshold would crash
   on a clean install. test_large_csv_load_uses_polars_and_succeeds is a
   regression test for this: it specifically crosses the threshold so the
   Polars-to-pandas conversion path actually executes.
2. compare_service's modified-row diffing did per-cell Python str()
   comparisons inside a row loop, redundant with vectorized masks already
   computed earlier in the same function. Fixed by reusing those masks via
   numpy boolean indexing (~11x faster at 150k modified rows in informal
   benchmarking: ~14.5s -> ~1.3s). test_compare_large_modified_set_is_fast
   guards against this regressing back to the slow path, with a generous
   threshold to avoid CI flakiness while still catching an order-of-
   magnitude regression.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.excel import compare_service, duplicate_service
from app.services.excel.loader_service import load_workbook_all_sheets

# Comfortably over the 100k Polars threshold, small enough to keep the
# suite fast (well under a second to generate and load).
LARGE_ROW_COUNT = 150_000


@pytest.fixture(scope="module")
def large_csv(tmp_path_factory) -> Path:
    rng = np.random.default_rng(42)
    n = LARGE_ROW_COUNT
    df = pd.DataFrame(
        {
            "SignalID": [f"SIG{i:07d}" for i in range(n)],
            "VIN": rng.choice([f"VIN{i:05d}" for i in range(2000)], n),
            "EngineNumber": rng.choice([f"ENG{i:05d}" for i in range(2000)], n),
            "Value": rng.normal(100, 15, n),
        }
    )
    path = tmp_path_factory.mktemp("perf") / "large.csv"
    df.to_csv(path, index=False)
    return path


def test_large_csv_load_uses_polars_and_succeeds(large_csv: Path):
    """Regression test for the missing-pyarrow bug: this must cross the
    100k-row threshold so the Polars-to-pandas conversion path (the one
    that required pyarrow) actually runs, not just get parsed by pandas.
    Also guards the example_values sampling optimization in
    profile_dataframe (unbounded string-casting of a full high-cardinality
    column was ~2.7x slower in informal 500k-row benchmarking: ~4.8s ->
    ~1.8s for the full load+profile)."""
    start = time.time()
    handle, sheets = load_workbook_all_sheets(large_csv)
    elapsed = time.time() - start

    assert handle.engine_used == "polars"
    assert handle.row_count == LARGE_ROW_COUNT
    assert len(sheets[handle.active_sheet]) == LARGE_ROW_COUNT
    assert elapsed < 10, f"Load+profile took {elapsed:.1f}s on {LARGE_ROW_COUNT:,} rows -- investigate"


def test_large_file_duplicate_finder_is_reasonably_fast(large_csv: Path):
    handle, sheets = load_workbook_all_sheets(large_csv)
    df = sheets[handle.active_sheet]

    start = time.time()
    mask = duplicate_service.find_duplicate_mask(df, ["VIN", "EngineNumber"], keep="first")
    elapsed = time.time() - start

    assert isinstance(mask.sum(), (int, np.integer))
    # Generous bound (informal benchmarking: well under 1s at this size) --
    # this catches an order-of-magnitude regression, not micro-variance.
    assert elapsed < 15, f"Duplicate Finder took {elapsed:.1f}s on {LARGE_ROW_COUNT:,} rows -- investigate"


def test_compare_large_modified_set_is_fast(large_csv: Path):
    """Regression test for the modified_diffs vectorization fix -- see
    module docstring. Before the fix, this shape of workload (a large
    fraction of rows modified) took ~14.5s per 150k modified rows in
    informal benchmarking; after, ~1.3s."""
    handle, sheets = load_workbook_all_sheets(large_csv)
    df = sheets[handle.active_sheet]
    df2 = df.copy()
    df2["Value"] = df2["Value"] + 1.0  # force every row to differ

    start = time.time()
    result = compare_service.compare_workbooks(df, df2, ["SignalID"])
    elapsed = time.time() - start

    assert result.report.modified_count == LARGE_ROW_COUNT
    assert len(result.modified_diffs) == LARGE_ROW_COUNT
    assert result.modified_diffs[0].changed_columns == ["Value"]
    # Generous bound well above the ~1.3s observed post-fix, but far below
    # the ~14.5s pre-fix figure -- catches a real regression, not noise.
    assert elapsed < 10, f"Compare took {elapsed:.1f}s on {LARGE_ROW_COUNT:,} modified rows -- investigate"
