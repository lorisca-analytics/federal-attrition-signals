# Data contract, version 1.0.0

The clean tables in `data/clean/` (copied to `dashboard/data/`) are the only output other things should read. Their exact shape is in `contract/tables.v1.json`. `python -m fas.contract data/clean` checks every file against it, and CI runs that check on every push.

## Rules

1. A column is never renamed or removed inside a major version. New columns go at the end of a table and bump the minor version (1.1.0).
2. A breaking change gets a new file (`tables.v2.json`) and a new major version. The old one stays until nothing reads it.
3. Every table with a rate carries the flags that say whether to trust it: `provisional` everywhere, `incomplete` and `gap_months` on agency rows.
4. Rates are per 100 employees. The denominator is the average of the September headcount before and at the end of the fiscal year.
5. Fiscal years run October to September and are named by the year they end in (FY2025 = Oct 2024 to Sep 2025).
6. `drp_` columns count separations OPM flags with `drp_indicator = Y` (the 2025 Deferred Resignation Program). They are a subset of the reason columns, never added to them.

## Tables

| Table | One row per | Use it for |
|---|---|---|
| `agency_year` | agency and fiscal year | Rates and reasons by agency. Rank only rows where `incomplete` is false. |
| `occupation_year` | occupational group and fiscal year | Rates by job type. Incomplete agency-years are already left out. |
| `reason_year` | fiscal year and reason segment | Why people left, government wide. Segments: Quit, Retirement or early out, DRP-flagged exit, Reduction in force, Transfer, termination or other. |
| `benchmark_year` | fiscal year and series | OPM federal quit rate next to BLS industries. |
| `agency_month` | agency and file month | Separations as reported each month, the usual level, and whether the month failed the check. |
| `coverage_gaps` | agency and file month | Only the months that failed the check. |

## What the checker refuses

- A missing table, a missing column, or contract columns in a different order
- A value of the wrong type, out of range, or not matching its pattern (agency codes are two characters, months are `yyyymm`)
- A duplicate key
- Agency reason columns that don't add up to `separations`
- A table with a rate and no trust flag

## Where each field comes from

| Field | Source |
|---|---|
| agency, agency_code, occupational_group | OPM separations and employment files, same names |
| reason | OPM `separation_category_code`: SC quit, SD and SG retirement, SE early out, SH reduction in force, SA and SB transfer, SJ termination or expired appointment, others "other" |
| fiscal_year | OPM `personnel_action_effective_date_yyyymm` |
| headcount | sum of OPM employment file `count` per September snapshot |
| BLS series | `JTS<industry>000000000QUR`, seasonally adjusted quits rate |
