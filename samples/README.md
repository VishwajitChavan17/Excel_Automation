# Sample Files

Realistic example workbooks for trying out each tool. Every file below has
been verified to produce the described result when run through the actual
tool.

| File | Try it with | What you'll see |
|---|---|---|
| `01_Signal_Mapping_Master.xlsx` | **Column Mapper** | 30 rows of `Signal Name` / `Description` / `Unit` -- map to a destination schema like `Signal` / `Comment` / `Engineering Unit` |
| `02_Fleet_Master.xlsx` | **Duplicate Finder** | 200 vehicle records (`VIN` + `Engine Number`) with **12 intentional duplicate rows** -- select both columns as the composite key and click Find Duplicates |
| `02_Fleet_Master.xlsx` + `03_Fleet_Second_Run.xlsx` | **Compare Excel** | Same fleet, a later test run: 10 rows removed (Missing In Second), 2 new VINs added (New In Second), 10 rows with a changed `Test Result` (Modified). Key column: `VIN` + `Engine Number` |
| `02_Fleet_Master.xlsx` (master) + `04_Lookup_Target.xlsx` (target) | **Lookup & Copy Values** | The target file only has `VIN` + `Engine Number` -- match on both columns (composite key) and copy `Model` and `Test Result` across from the master |
| `05_Employees_SiteA.xlsx` + `06_Employees_SiteB.xlsx` | **Merge Files** (Union) or **Consolidate Files** | Two sites' employee rosters with an identical header -- union-merge or auto-consolidate them into one master list, tagged with Source File |
| `06_Employees_SiteB.xlsx` | **Validation Rules** | Contains **one intentional blank Name** and **one intentional negative Salary** -- add a `Required` rule on `Name` and a `No Negative Values` rule on `Salary`, then Run Validation to see both issues |

## Suggested first walkthrough

1. **File > Open Folder...** and select this `samples/` folder to load
   everything at once.
2. Open **Duplicate Finder** (ribbon: Excel), pick `02_Fleet_Master.xlsx`,
   select `VIN` + `Engine Number`, Find Duplicates -- see 12 flagged.
3. Open **Compare Excel** (ribbon: Compare), Master =
   `02_Fleet_Master.xlsx`, Second = `03_Fleet_Second_Run.xlsx`, key =
   `VIN` + `Engine Number` -- see the three result grids populate.
4. Open **Validation Rules** (ribbon: Validation), pick
   `06_Employees_SiteB.xlsx`, add the two rules described above, Run
   Validation -- see exactly 2 issues.
5. Try **Merge Files** (ribbon: Merge) with the two employee files to see
   a 90-row union with a `Source File` column added.

None of these operations touch the files in this folder -- every tool
works on an in-memory copy, so feel free to experiment freely.
