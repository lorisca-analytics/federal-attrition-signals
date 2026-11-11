"""Build the clean tables from data/raw and export them as CSV.

Usage:
    python -m fas.build            # data/raw -> data/clean/*.csv and dashboard/data/*.csv
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
DASH = ROOT / "dashboard" / "data"

# Thresholds in one place. DECISIONS.md explains each one.
PARAMS = {
    "first_month": "201107",       # headcount is monthly from here
    "min_headcount": 1000,         # smaller agencies swing too much to rank
    "min_baseline": 20,            # coverage check only where an agency normally reports 20+ a month
    "gap_ratio": 0.25,             # under a quarter of its own recent median = gap
    "min_band_headcount": 100,     # length-of-service bands smaller than this are left out
    "provisional_from_fy": 2026,   # late records for this year are still arriving
}

EXPORTS = {
    "agency_year": "select * from agency_year order by fiscal_year, agency_code",
    "occupation_year": "select * from occupation_year order by fiscal_year, occupational_group",
    "benchmark_year": "select * from benchmark_year order by fiscal_year, series",
    "reason_year": "select * from reason_year order by fiscal_year, segment",
    "service_year": """
        select * from service_year order by fiscal_year, agency_code,
        list_position(['under 1', '1 to 2', '3 to 4', '5 to 9', '10 to 19', '20 or more'], service_band)""",
    "agency_month": """
        select c.agency_code, n.agency, c.file_month, c.separations, c.baseline, c.is_gap
        from coverage c join agency_names n using (agency_code)
        order by c.agency_code, c.file_month""",
    "coverage_gaps": """
        select c.agency_code, n.agency, c.file_month, c.fiscal_year, c.separations, c.baseline
        from coverage c join agency_names n using (agency_code)
        where c.is_gap order by c.file_month, c.agency_code""",
}


def current_files(raw: Path, dataset: str) -> list[tuple[str, Path]]:
    m = json.loads((raw / "manifest.json").read_text())["files"]
    out = []
    for key, rec in sorted(m.items()):
        ds, y, mo = key.split("/")
        if ds == dataset:
            out.append((y + mo, raw / rec["file"]))
    return out


def connect(raw: Path, params: dict | None = None) -> duckdb.DuckDBPyConnection:
    p = {**PARAMS, **(params or {})}
    con = duckdb.connect()
    con.execute("create table params as select * from (select " + ", ".join(
        f"?::{'varchar' if isinstance(v, str) else 'double'} as {k}" for k, v in p.items()) + ")",
        list(p.values()))

    def union(dataset: str, month_col: str) -> str:
        files = current_files(raw, dataset)
        if not files:
            raise SystemExit(f"no {dataset} files in {raw}, run: python -m fas.pull")
        parts = [f"select *, '{ym}' as {month_col} from read_parquet('{f.as_posix()}')" for ym, f in files]
        return " union all by name ".join(parts)

    con.execute(f"create view raw_separations as {union('separations', 'file_month')}")
    con.execute(f"create view raw_employment as {union('employment', 'snapshot_month')}")
    jolts = raw / "jolts.json"
    if jolts.exists():
        con.execute(f"create table jolts as select * from read_json_auto('{jolts.as_posix()}')")
    else:
        con.execute("create table jolts (industry varchar, measure varchar, year int, month int, rate double)")
    return con


def build(raw: Path = RAW, out_dirs: tuple[Path, ...] = (CLEAN, DASH), params: dict | None = None):
    con = connect(raw, params)
    con.execute((ROOT / "sql" / "build.sql").read_text())
    for d in out_dirs:
        d.mkdir(parents=True, exist_ok=True)
    for name, q in EXPORTS.items():
        target = out_dirs[0] / f"{name}.csv"
        con.execute(f"copy ({q}) to '{target.as_posix()}' (header, delimiter ',')")
        for d in out_dirs[1:]:
            shutil.copyfile(target, d / f"{name}.csv")
    return con


if __name__ == "__main__":
    con = build()
    for name in EXPORTS:
        print(name, con.execute(f"select count(*) from ({EXPORTS[name]})").fetchone()[0], "rows")
