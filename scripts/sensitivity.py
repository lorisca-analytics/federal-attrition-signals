"""How many agency-months fail the coverage check under different thresholds?

Usage: python scripts/sensitivity.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fas.build import RAW, build  # noqa: E402

print("gap_ratio  min_baseline  gap_months  agencies  incomplete_agency_years")
for ratio in (0.2, 0.25, 0.33, 0.5):
    for floor in (10, 20, 50):
        con = build(raw=RAW, out_dirs=(Path("/tmp/fas-sensitivity"),), params={"gap_ratio": ratio, "min_baseline": floor})
        g, a = con.execute("select count(*), count(distinct agency_code) from coverage where is_gap").fetchall()[0]
        y = con.execute("select count(*) from agency_year where incomplete").fetchall()[0][0]
        print(f"{ratio:>9}  {floor:>12}  {g:>10}  {a:>8}  {y:>23}")
