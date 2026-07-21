# Performance

Excel Automation Studio targets files in the hundreds-of-thousands-of-rows
range (500,000+ rows per the original spec). This document records actual
measured numbers, not estimates, from a synthetic 500,000-row benchmark
run during Phase 6, plus two real performance bugs found and fixed as a
direct result of that benchmarking.

## Benchmark setup

A synthetic 500,000-row, 6-column CSV (~35 MB), representative of an
engineering signal export: `SignalID` (unique), `VIN` / `EngineNumber`
(2,000 distinct values each, so duplicates exist), `Value` (float,
normally distributed, high-cardinality), `Unit` (5 distinct values),
`Timestamp`.

All numbers below are wall-clock time for the operation only (file
generation excluded), measured on a single run on ordinary
(non-server-grade) hardware -- treat them as evidence of "fast enough for
interactive use," not a formal SLA.

## Results (500,000 rows, after fixes)

| Operation | Time | Notes |
|---|---|---|
| Load + full column profiling | **1.96s** | Includes switching to the Polars parser (row count is above the 100k threshold) and computing every column's null%/unique%/duplicate%/min/max/examples |
| Duplicate Finder (composite key, 2 columns) | **0.04s** | 5,126 duplicates found among 500k rows |
| Remove Duplicates | **0.06s** | |
| Validation (3 rules: required, numeric, no-negative) | **<0.01s** | |
| Compare (500k rows vs. 500k rows, **every row modified**) | **2.78s** | Worst case: forces the largest possible `modified` result set |
| Union Merge (2x 250k rows -> 500k) | **0.02s** | |

All of the above ran comfortably within a few seconds -- well inside what
feels responsive for an interactive desktop tool, especially since every
one of these operations runs on a background thread with a progress bar
rather than blocking the UI regardless of how long it takes.

## Two real bugs found via this benchmarking

Both are also covered by permanent regression tests in
`tests/test_phase6_performance.py` (using a smaller ~150k-row fixture to
keep the test suite itself fast).

### 1. Missing `pyarrow` dependency (correctness bug, not just performance)

`polars.DataFrame.to_pandas()` -- the conversion step used after Polars
parses a large CSV/TSV -- requires `pyarrow`. It was never listed in
`requirements.txt`. **Any CSV/TSV file over the 100,000-row threshold
would crash on a clean install**, immediately after the fast Polars parse
completed. Found the moment the first 500k-row benchmark ran; fixed by
adding `pyarrow>=16.0` to `requirements.txt`.

### 2. Compare's modified-row diffing (~11x slowdown at scale)

`compare_service.compare_workbooks()`'s construction of `modified_diffs`
(the per-row list of "which columns changed") originally did per-cell
`str(a) != str(b)` comparisons inside a Python `for _, row in
modified.iterrows(): ...` loop -- redundant with the vectorized diff
masks the same function had already computed one column at a time just
above it. At 150,000 modified rows (informal benchmarking): **~14.5s**
before the fix, **~1.3s** after, by reusing the already-computed masks
via numpy boolean array indexing instead of recomputing string
comparisons per cell per row. At the full 500k-row / 500k-modified-row
worst case shown in the table above, the fixed version takes 2.78s total
for the entire compare (mask computation + vectorized diff extraction).

## Other tuning applied

- **`profile_dataframe`'s example-value sampling** now bounds the
  (relatively expensive, since it's a full string cast) scan to the first
  200 non-null values per column instead of casting every value in the
  column just to keep 5 examples. This was the dominant per-column cost
  for high-cardinality numeric columns (~0.58s for a single 500k-row
  float column before the fix). Full-load time for the 500k-row benchmark
  dropped from ~4.8s to ~1.96s as a result.
- **Length statistics (`min_length`/`max_length`) intentionally still scan
  the full column** -- unlike example values, a true min/max needs every
  row, and this is a linear (not quadratic) cost, so it was left as-is
  after confirming via profiling it wasn't the dominant cost.

## Configuring performance behavior

Settings -> Performance exposes:

- **Large-file row threshold** (default 100,000) -- the CSV/TSV row count
  above which loading switches from pandas to Polars.
- **Max background worker threads** (default 4) -- currently informational/
  reserved for a future thread-pool-based batch scheduler; today each
  operation runs on its own dedicated `QThread` rather than a shared pool.
- **Use Polars automatically** -- toggle to force pandas-only loading if
  ever needed for debugging.

## Known scaling characteristics to be aware of

- Compare's cost scales primarily with the size of the **modified** row
  set, not the total row count -- two 500k-row files that are 99% identical
  compare far faster than two files where most rows differ (as shown in
  the worst-case row above).
- `.xlsx`/`.xls` loading always goes through `pandas` + `openpyxl` (never
  Polars, which only accelerates the CSV/TSV path) -- Excel's binary
  formats don't have a fast-path parser wired up in this app. For files
  in the hundreds-of-thousands-of-rows range, CSV/TSV will load
  substantially faster than the equivalent `.xlsx`.
