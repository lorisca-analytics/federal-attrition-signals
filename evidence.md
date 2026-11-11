# Evidence

How each finding in the README can be checked, and why each call was made.

## Every number has a source

`python scripts/findings.py` recomputes every number the README and card quote and writes them to `docs/findings.json`. The keys:

| README claim | Key in docs/findings.json |
|---|---|
| 183 monthly files, about 3.8 million rows | `separations_files`, `separation_rows_total` |
| Army 2,430 then 9, Air Force 2,220 then 26, usual months about 1,860 and 1,300 | `army_airforce` |
| Army 180,217 and Air Force 150,492 employed in Sep 2026 | `army_airforce_headcount_202609` |
| 29 agency-months in 14 agencies fail the check | `gap_months_total`, `gap_agencies` |
| About one in five rows in the Sep 2026 file left earlier | `late_share_202609` |
| About 109,000 exit-program separations in FY2025 | `drp_exits_2025` |
| Quit rate 3.57 (FY2024), 7.04 (FY2025), 4.2 without exit-program quits | `gov_quit_rate`, `gov_quit_rate_without_drp_2025` |
| Commerce 12 of 12, Interior 11 of 12, Agriculture 10 of 11, Defense offices 10 of 13 | `top5_streaks_fy2012_2024` |
| General services and support work 9.56, information technology 1.96 | `occupation_fy2024_high_low` |
| OPM 3.57, BLS federal 6.4, all jobs 25.8 (FY2024) | `benchmark_fy2024` |
| Agency for International Development headcount 4,800, 1,101, 230 | `usaid_headcount`, `usaid_headcount_202609` |

## Why each call was made

The full reasoning, with the options I turned down, is in [DECISIONS.md](DECISIONS.md). In short:

- **Coverage before ranking**, because a missing submission and a calm month look the same in the raw counts.
- **Effective month, not file month**, because a person belongs to the year they left.
- **Exit programs apart**, because they are a policy event, not a change in how many people chose to quit.
- **September headcounts**, because yearly rates don't need 9 GB of monthly snapshots.
- **A data contract with a checker in CI**, because the dashboard and anyone reusing the CSVs depend on the columns staying put.

## Outside sources

- OPM Federal Workforce Data, API and downloads: https://data.opm.gov/get-data/api-access
- OPM coverage notes (what EHRI includes and excludes): https://data.opm.gov/resources/data-sources
- OPM description of the Deferred Resignation Program and its separation types: https://data.opm.gov/explore-data/analytics/workforce-changes
- OPM notice on incomplete September 2026 Department of War data: https://data.opm.gov/
- BLS series ID format: https://www.bls.gov/help/hlpforma.htm
- BLS JOLTS industry and data element codes: https://download.bls.gov/pub/time.series/jt/
