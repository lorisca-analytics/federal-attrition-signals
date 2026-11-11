import json
import shutil
from pathlib import Path

from fas import contract

SPEC = json.loads(contract.CONTRACT.read_text())


def write_table(folder: Path, name: str, rows: list[dict]):
    cols = list(SPEC["tables"][name]["columns"])
    lines = [",".join(cols)] + [",".join(str(r[c]) for c in cols) for r in rows]
    (folder / f"{name}.csv").write_text("\n".join(lines) + "\n")


GOOD_AGENCY = {
    "fiscal_year": 2024, "agency_code": "VA", "agency": "DEPARTMENT OF VETERANS AFFAIRS",
    "start_headcount": 1000, "end_headcount": 1000, "avg_headcount": 1000, "separations": 10, "quits": 4, "retirements": 3, "early_outs": 0,
    "reductions_in_force": 0, "transfers": 1, "terminations_or_expired": 1, "other": 1,
    "drp_separations": 0, "drp_quits": 0, "quit_rate": 0.4, "quit_rate_excl_drp": 0.4, "separation_rate": 1.0,
    "core_avg_headcount": 900, "core_quits": 3, "core_quit_rate": 0.33, "incomplete": "false", "gap_months": 0, "provisional": "false",
}


def good_folder(tmp_path):
    write_table(tmp_path, "agency_year", [GOOD_AGENCY])
    write_table(tmp_path, "occupation_year", [{
        "fiscal_year": 2024, "occupational_group": "LEGAL AND KINDRED GROUP", "avg_headcount": 50,
        "separations": 2, "quits": 1, "drp_quits": 0, "quit_rate": 2.0, "quit_rate_excl_drp": 2.0, "separation_rate": 4.0,
        "core_quits": 1, "core_quit_rate": 2.5, "provisional": "false"}])
    write_table(tmp_path, "benchmark_year", [{
        "fiscal_year": 2024, "series": "Federal (BLS)", "quit_rate": 7.2, "provisional": "false"}])
    write_table(tmp_path, "reason_year", [{
        "fiscal_year": 2024, "segment": "Quit", "separations": 5, "rate": 3.5, "provisional": "false"}])
    write_table(tmp_path, "agency_month", [
        {"agency_code": "AR", "agency": "DEPARTMENT OF THE ARMY", "file_month": "201107",
         "separations": 2000, "baseline": "", "is_gap": "false"},
        {"agency_code": "AR", "agency": "DEPARTMENT OF THE ARMY", "file_month": "202609",
         "separations": 9, "baseline": 1861.5, "is_gap": "true"}])
    write_table(tmp_path, "coverage_gaps", [{
        "agency_code": "AR", "agency": "DEPARTMENT OF THE ARMY", "file_month": "202609",
        "fiscal_year": 2026, "separations": 9, "baseline": 2400.0}])
    return tmp_path


def test_good_tables_pass(tmp_path):
    assert contract.validate(good_folder(tmp_path)) == []


def test_removed_column_fails(tmp_path):
    folder = good_folder(tmp_path)
    p = folder / "agency_year.csv"
    lines = p.read_text().splitlines()
    cut = [",".join(l.split(",")[:-1]) for l in lines]  # drop the provisional flag
    p.write_text("\n".join(cut) + "\n")
    errs = contract.validate(folder)
    assert any("missing ['provisional']" in e for e in errs)


def test_added_column_at_the_end_is_allowed(tmp_path):
    folder = good_folder(tmp_path)
    p = folder / "benchmark_year.csv"
    lines = p.read_text().splitlines()
    p.write_text("\n".join([lines[0] + ",note"] + [l + ",x" for l in lines[1:]]) + "\n")
    assert contract.validate(folder) == []


def test_reasons_must_add_up(tmp_path):
    folder = good_folder(tmp_path)
    write_table(folder, "agency_year", [{**GOOD_AGENCY, "separations": 11}])
    assert any("do not add up" in e for e in contract.validate(folder))


def test_bad_values_fail(tmp_path):
    folder = good_folder(tmp_path)
    write_table(folder, "agency_year", [{**GOOD_AGENCY, "quit_rate": -1, "incomplete": "maybe"},
                                        {**GOOD_AGENCY}])
    errs = contract.validate(folder)
    assert any("quit_rate=-1.0 below 0" in e for e in errs)
    assert any("not a bool" in e for e in errs)
    assert any("duplicate key" in e for e in errs)


def test_missing_table_fails(tmp_path):
    folder = good_folder(tmp_path)
    (folder / "coverage_gaps.csv").unlink()
    assert contract.validate(folder) == ["coverage_gaps: file missing (coverage_gaps.csv)"]
