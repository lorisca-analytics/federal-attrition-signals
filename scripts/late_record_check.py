"""How often does a late record look exactly like a row in the previous month's file?

OPM files have no person ID, so a separation can't be matched across files for certain.
This compares the late rows in one file (effective in the previous month) with the
previous file, and also counts identical rows inside a single file. If identical rows are
common inside one file, identical rows across files are not proof of double counting.

Usage: python scripts/late_record_check.py 2026 09
"""
import json
import sys
from pathlib import Path

import duckdb

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def main(year: str, month: str):
    files = json.loads((RAW / "manifest.json").read_text())["files"]
    py, pm = (int(year), int(month) - 1) if month != "01" else (int(year) - 1, 12)
    prev_month = f"{py}{pm:02d}"
    cur = RAW / files[f"separations/{year}/{month}"]["file"]
    prev = RAW / files[f"separations/{py}/{pm:02d}"]["file"]
    con = duckdb.connect()
    late = con.execute(f"select count(*) from '{cur}' where personnel_action_effective_date_yyyymm = '{prev_month}'").fetchall()[0][0]
    cross = con.execute(f"""select count(*) from (
        select * exclude (count) from '{cur}' where personnel_action_effective_date_yyyymm = '{prev_month}'
        intersect all select * exclude (count) from '{prev}')""").fetchall()[0][0]
    out = {"file": f"{year}{month}", "late_rows_effective_previous_month": late,
           "identical_to_a_row_in_previous_file": cross}
    for label, f in (("previous_file", prev), ("this_file", cur)):
        n = con.execute(f"select count(*) from '{f}'").fetchall()[0][0]
        u = con.execute(f"select count(*) from (select distinct * exclude (count) from '{f}')").fetchall()[0][0]
        out[f"{label}_rows"] = n
        out[f"{label}_identical_rows_inside"] = n - u
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
