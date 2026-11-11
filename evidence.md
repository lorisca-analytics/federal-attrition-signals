# Evidence

How each finding in the README can be checked, and why each call was made.

## Every number has a source

`python scripts/findings.py` recomputes every number the README and card quote and writes them to `docs/findings.json`. The keys:

| README claim | Key in docs/findings.json |
|---|---|
| 183 monthly files, about 3.8 million rows, 12 baseline-only files | `separations_files_in_window`, `separation_rows_in_window`, `separations_files_baseline_only` |
| Army 2,430 then 9, Air Force 2,220 then 26, usual months about 1,860 and 1,300 | `army_airforce` |
| Army 180,217 and Air Force 150,492 employed in Sep 2026 | `army_airforce_headcount_202609` |
| 17 agency-months fail the check | `gap_months_total`, `gap_agencies` |
| About one in five rows in the Sep 2026 file left earlier | `late_share_202609` |
| About 110,000 exit-program separations in FY2025 | `drp_exits_2025_all` (`drp_exits_2025_covered` for agencies I could rank) |
| Seasonal and temporary jobs about 8% of headcount, 28% of quits (FY2024) | `core_share_fy2024` |
| Commerce 768 of 2,384 quits, 4.89 falling to 1.85 | `commerce_fy2024` |
| Quit rate 3.57 (FY2024), 7.04 (FY2025), 4.2 without exit-program quits, 2.80 permanent staff | `gov_quit_rate`, `gov_quit_rate_without_drp_2025`, `gov_core_quit_rate` |
| VA and Army 13 of 13, Defense offices 12, Homeland Security 11 (permanent staff) | `top5_streaks_core_fy2012_2024` |
| Commerce 13 of 13, Interior 12, Agriculture 11 (all staff), none in the permanent-staff top five | `top5_streaks_fy2012_2024`, `raw_leaders_core_top5_years` |
| General services 7.44, food preparation 5.84, equipment 1.56, information technology 1.62 | `occupation_core_fy2024_high_low` |
| OPM 3.57, BLS federal 6.4, all jobs 25.8 (FY2024), correlation 0.76 | `benchmark_fy2024`, `opm_bls_federal_correlation_fy2012_2024` |
| Agency for International Development headcount 4,800, 1,101, 230 | `usaid_headcount`, `usaid_headcount_202609` |
| Monthly headcount about 12.6 GB, snapshots about 1.1 GB | `employment_bytes_avg` x 183, `employment_bytes_total` |

The threshold table is in `docs/sensitivity.txt`, from `python scripts/sensitivity.py`.

## Why each call was made

The full reasoning, with the options I turned down, is in [DECISIONS.md](DECISIONS.md). In short:

- **Coverage before ranking**, because a missing submission and a calm month look the same in the raw counts.
- **Permanent staff ranked apart**, because seasonal and temporary jobs end on a schedule and push seasonal employers to the top.
- **Effective month over file month**, because a person belongs to the year they left.
- **Exit programs apart**, because a program that offered paid leave before separation changes who leaves and when, and mixing it in hides the ordinary quit rate.
- **September headcounts**, because yearly rates don't need 12.6 GB of monthly snapshots.
- **A data contract with a checker in CI**, because the dashboard and anyone reusing the CSVs depend on the columns staying put.

## Outside sources

- OPM Federal Workforce Data, API: https://data.opm.gov/get-data/api-access
- OPM coverage notes (what EHRI includes and excludes): https://data.opm.gov/resources/data-sources
- OPM description of the Deferred Resignation Program and its separation types: https://data.opm.gov/explore-data/analytics/workforce-changes
- OPM notice on September 2026 Department of War data: https://data.opm.gov/
- BLS JOLTS overview (monthly survey of about 21,000 establishments): https://www.bls.gov/jlt/jltover.htm
- BLS series ID format: https://www.bls.gov/help/hlpforma.htm
