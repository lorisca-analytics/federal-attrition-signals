"""Profile the raw separations and headcount files that feed the analysis.

Usage: python scripts/profile.py   (writes docs/data-profile.json)
"""
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fas.build import RAW, current_files  # noqa: E402

con = duckdb.connect()
sep = [p.as_posix() for ym, p in current_files(RAW, "separations") if ym >= "201107"]
emp = [p.as_posix() for _, p in current_files(RAW, "employment")]
con.execute(f"create view s as select * from read_parquet({sep}, union_by_name=true, filename=true)")
con.execute(f"create view e as select * from read_parquet({emp}, union_by_name=true)")


def q(sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


cols = ["agency_code", "occupational_group", "separation_category_code", "personnel_action_effective_date_yyyymm",
        "tenure_code", "work_schedule_code", "drp_indicator", "count"]
p = {"rows": q("select count(*) as n from s")[0]["n"]}
p["columns"] = {}
for c in cols:
    p["columns"][c] = q(f"""
        select count(*) filter (where {c} is null) as nulls,
               count(*) filter (where trim(cast({c} as varchar)) in ('', '*')) as blank_or_invalid,
               count(distinct {c}) as distinct_values
        from s""")[0]
p["count_values"] = q("select count, count(*) as n from s group by 1 order by 2 desc limit 3")
p["effective_range"] = q("select min(personnel_action_effective_date_yyyymm) as min, max(personnel_action_effective_date_yyyymm) as max from s")[0]
p["effective_after_file_month"] = q("""
    select count(*) as n from s
    where personnel_action_effective_date_yyyymm > regexp_extract(filename, '_(\\d{6})_', 1)""")[0]["n"]
p["effective_more_than_12_months_before_file"] = q("""
    select count(*) as n from s
    where personnel_action_effective_date_yyyymm <
          strftime(strptime(regexp_extract(filename, '_(\\d{6})_', 1), '%Y%m') - interval 12 month, '%Y%m')""")[0]["n"]
p["category_codes"] = q("select separation_category_code as code, any_value(separation_category) as label, count(*) as n from s group by 1 order by 3 desc")
p["occupational_group_null_by_year"] = q("""
    select substr(personnel_action_effective_date_yyyymm, 1, 4) as year,
           round(avg((occupational_group is null)::int), 4) as null_share
    from s group by 1 having null_share > 0 order by 1""")
p["headcount_rows"] = q("select count(*) as n from e")[0]["n"]
p["headcount_blank_tenure_or_schedule"] = q("""
    select round(avg((trim(coalesce(tenure_code, '')) in ('', '*') or trim(coalesce(work_schedule_code, '')) in ('', '*'))::int), 4) as share from e""")[0]["share"]
p["separations_blank_tenure_or_schedule"] = q("""
    select round(avg((trim(coalesce(tenure_code, '')) in ('', '*') or trim(coalesce(work_schedule_code, '')) in ('', '*'))::int), 4) as share from s""")[0]["share"]
p["agency_codes_without_headcount"] = q("""
    select count(distinct s.agency_code) as n, count(*) as rows from s
    left join (select distinct agency_code from e) h using (agency_code) where h.agency_code is null""")[0]

out = ROOT / "docs" / "data-profile.json"
out.write_text(json.dumps(p, indent=1, default=str))
print(json.dumps(p, indent=1, default=str))
