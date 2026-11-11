"""Print every number the README quotes, from the clean tables and the raw files.

Usage: python scripts/findings.py   (writes docs/findings.json)
Each README number points to a key in that file, so a reader can check it.
"""
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fas.build import current_files, RAW  # noqa: E402

CLEAN = ROOT / "data" / "clean"
con = duckdb.connect()
for t in ("agency_year", "occupation_year", "benchmark_year", "reason_year", "coverage_gaps", "agency_month"):
    path = (CLEAN / (t + ".csv")).as_posix()
    header = (CLEAN / (t + ".csv")).read_text().splitlines()[0].split(",")
    types = {c: "VARCHAR" for c in ("file_month", "agency_code") if c in header}
    con.execute(f"create view {t} as select * from read_csv_auto('{path}', types={types})")


def one(sql):
    return con.execute(sql).fetchall()[0][0]


def rows(sql):
    cols = [d[0] for d in con.execute(sql).description]
    return [dict(zip(cols, r)) for r in con.execute(sql).fetchall()]


f = {}
f["window"] = rows("select min(fiscal_year) as first_fy, max(fiscal_year) as last_fy from agency_year")[0]
f["separations_files"] = len(current_files(RAW, "separations"))
f["headcount_snapshots"] = len(current_files(RAW, "employment"))
f["separation_rows_in_window"] = one(
    "select count(*) from read_parquet([" + ",".join(f"'{p.as_posix()}'" for ym, p in current_files(RAW, "separations") if ym >= "201107") + "], union_by_name=true)")
f["separations_files_in_window"] = sum(1 for ym, _ in current_files(RAW, "separations") if ym >= "201107")
f["separations_files_baseline_only"] = sum(1 for ym, _ in current_files(RAW, "separations") if ym < "201107")
f["employment_bytes_avg"] = round(sum(p.stat().st_size for _, p in current_files(RAW, "employment")) / len(current_files(RAW, "employment")))
f["employment_bytes_total"] = sum(p.stat().st_size for _, p in current_files(RAW, "employment"))

f["gap_months_total"] = one("select count(*) from coverage_gaps")
f["gap_agencies"] = one("select count(distinct agency_code) from coverage_gaps")
f["army_airforce"] = rows("""
    select agency_code, file_month, separations, baseline from agency_month
    where agency_code in ('AR', 'AF') and file_month in ('202409', '202608', '202609') order by 1, 2""")
f["army_airforce_headcount_202609"] = rows("""
    select agency_code, end_headcount from agency_year
    where agency_code in ('AR', 'AF') and fiscal_year = 2026 order by 1""")

f["gov_quit_rate"] = rows("""
    select fiscal_year, quit_rate from benchmark_year
    where series = 'Federal civilian (OPM, covered agencies)' and fiscal_year in (2019, 2022, 2024, 2025) order by 1""")
f["gov_core_quit_rate"] = rows("""
    select fiscal_year, quit_rate from benchmark_year
    where series = 'Federal civilian (OPM), permanent non-seasonal staff' and fiscal_year in (2024, 2025) order by 1""")
f["gov_quit_rate_without_drp_2025"] = one("""
    select quit_rate from benchmark_year
    where series like '%without DRP%' and fiscal_year = 2025""")
f["drp_exit_rate_2025"] = one("select rate from reason_year where fiscal_year = 2025 and segment = 'DRP-flagged exit'")
f["drp_exits_2025_covered"] = one("select separations from reason_year where fiscal_year = 2025 and segment = 'DRP-flagged exit'")
sep_files = [p for _, p in current_files(RAW, "separations")]
f["drp_exits_2025_all"] = one(
    "select count(*) from read_parquet([" + ",".join(f"'{p.as_posix()}'" for p in sep_files) + "], union_by_name=true) "
    "where drp_indicator = 'Y' and personnel_action_effective_date_yyyymm between '202410' and '202509'")
f["drp_quits_2025"] = one("select sum(drp_quits) from agency_year where fiscal_year = 2025 and not incomplete")

f["top5_streaks_fy2012_2024"] = rows("""
    with r as (
        select fiscal_year, agency, rank() over (partition by fiscal_year order by quit_rate desc) as rk
        from agency_year where not incomplete and fiscal_year <= 2024 and avg_headcount >= 5000)
    select agency, count(*) filter (where rk <= 5) as years_in_top5, count(*) as years_ranked
    from r group by agency having count(*) filter (where rk <= 5) >= 10 order by 2 desc""")
f["top5_streaks_core_fy2012_2024"] = rows("""
    with r as (
        select fiscal_year, agency, rank() over (partition by fiscal_year order by core_quit_rate desc) as rk
        from agency_year where not incomplete and fiscal_year <= 2024 and avg_headcount >= 5000)
    select agency, count(*) filter (where rk <= 5) as years_in_top5, count(*) as years_ranked
    from r group by agency having count(*) filter (where rk <= 5) >= 10 order by 2 desc""")
f["raw_leaders_core_top5_years"] = rows("""
    with r as (
        select fiscal_year, agency_code, agency, rank() over (partition by fiscal_year order by core_quit_rate desc) as rk
        from agency_year where not incomplete and fiscal_year <= 2024 and avg_headcount >= 5000)
    select agency, count(*) filter (where rk <= 5) as years_in_top5_permanent from r
    where agency_code in ('CM', 'IN', 'AG') group by agency order by agency""")
f["core_share_fy2024"] = rows("""
    select round(100.0 * sum(core_quits) / sum(quits), 1) as core_share_of_quits,
           round(100.0 * sum(core_avg_headcount) / sum(avg_headcount), 1) as core_share_of_headcount
    from agency_year where fiscal_year = 2024 and not incomplete""")[0]
f["commerce_fy2024"] = rows("""
    select quit_rate, core_quit_rate, quits, core_quits from agency_year
    where agency_code = 'CM' and fiscal_year = 2024""")[0]
f["occupation_core_fy2024_high_low"] = rows("""
    (select occupational_group, avg_headcount, core_quit_rate from occupation_year
     where fiscal_year = 2024 and avg_headcount >= 10000 order by core_quit_rate desc limit 3)
    union all
    (select occupational_group, avg_headcount, core_quit_rate from occupation_year
     where fiscal_year = 2024 and avg_headcount >= 10000 order by core_quit_rate asc limit 3)""")
f["opm_bls_federal_correlation_fy2012_2024"] = one("""
    select round(corr(o.quit_rate, b.quit_rate), 2) from benchmark_year o join benchmark_year b using (fiscal_year)
    where o.series = 'Federal civilian (OPM, covered agencies)' and b.series = 'Federal (BLS)' and fiscal_year <= 2024""")
f["agencies_ranked_fy2024"] = one(
    "select count(*) from agency_year where fiscal_year = 2024 and not incomplete and avg_headcount >= 5000")

f["occupation_fy2024_high_low"] = rows("""
    (select occupational_group, avg_headcount, quit_rate from occupation_year
     where fiscal_year = 2024 and avg_headcount >= 10000 order by quit_rate desc limit 3)
    union all
    (select occupational_group, avg_headcount, quit_rate from occupation_year
     where fiscal_year = 2024 and avg_headcount >= 10000 order by quit_rate asc limit 3)""")

f["benchmark_fy2024"] = rows("select series, quit_rate from benchmark_year where fiscal_year = 2024 order by quit_rate")

f["usaid_headcount"] = rows("""
    select fiscal_year, start_headcount, end_headcount, separations, separation_rate from agency_year
    where agency_code = 'AM' and fiscal_year >= 2024 order by 1""")
emp_2026 = [p for ym, p in current_files(RAW, "employment") if ym == "202609"]
if emp_2026:
    f["usaid_headcount_202609"] = one(f"select sum(cast(count as int)) from '{emp_2026[0].as_posix()}' where agency_code = 'AM'")
sep_2026 = [p for ym, p in current_files(RAW, "separations") if ym == "202609"]
if sep_2026:
    f["late_share_202609"] = one(f"""select round(avg((personnel_action_effective_date_yyyymm < '202609')::int), 3)
        from '{sep_2026[0].as_posix()}'""")

out = ROOT / "docs" / "findings.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(f, indent=1, default=str))
print(json.dumps(f, indent=1, default=str))
