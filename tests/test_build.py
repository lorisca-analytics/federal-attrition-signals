"""Build tests on small synthetic files shaped like the OPM ones."""
import csv
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from fas import build, contract

PARAMS = {"min_headcount": 10, "min_baseline": 3, "min_band_headcount": 10, "provisional_from_fy": 2099}


def months(start, end):
    y, m = int(start[:4]), int(start[4:])
    out = []
    while f"{y}{m:02d}" <= end:
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def sep_rows(agency_code, agency, effective, n_quit, n_retire, group="ACCOUNTING AND BUDGET GROUP", drp="N",
             tenure="1", schedule="F"):
    rows = []
    for code, n in (("SC", n_quit), ("SD", n_retire)):
        rows += [{
            "agency_code": agency_code, "agency": agency, "occupational_group": group,
            "separation_category_code": code, "personnel_action_effective_date_yyyymm": effective,
            "drp_indicator": drp, "count": "1", "tenure_code": tenure, "work_schedule_code": schedule,
            "length_of_service_years": "0.5",
        } for _ in range(n)]
    return rows


@pytest.fixture
def raw(tmp_path):
    files = {}

    def write(dataset, ym, rows):
        name = f"{dataset}_{ym}_v1.parquet"
        pq.write_table(pa.Table.from_pylist(rows), tmp_path / name)
        files[f"{dataset}/{ym[:4]}/{ym[4:]}"] = {"version": 1, "file": name}

    for ym in months("201007", "201310"):
        rows = []
        # AA reports every month: 2 quits and 3 retirements
        rows += sep_rows("AA", "AGENCY A", ym, 2, 3)
        # BB reports the same, except file 201303 arrives almost empty
        if ym == "201303":
            rows += sep_rows("BB", "AGENCY B", ym, 0, 0)
        else:
            rows += sep_rows("BB", "AGENCY B", ym, 2, 3)
        if ym == "201310":  # late record: processed in October, effective in September
            rows += sep_rows("AA", "AGENCY A", "201309", 1, 0)
        if ym == "201306":  # one exit flagged as part of the deferred resignation program
            rows += sep_rows("AA", "AGENCY A", ym, 1, 0, drp="Y")
        if ym == "201307":  # one seasonal employee quits
            rows += sep_rows("AA", "AGENCY A", ym, 1, 0, schedule="G")
        # CC is seasonal: every January it reports far fewer than its other months
        rows += sep_rows("CC", "AGENCY C", ym, 1 if ym.endswith("01") else 8, 0)
        write("separations", ym, rows)

    for ym in ("201109", "201209", "201309"):
        write("employment", ym, [
            {"agency_code": a, "agency": n, "occupational_group": "ACCOUNTING AND BUDGET GROUP",
             "count": "1", "snapshot_yyyymm": ym, "tenure_code": "1" if i < 90 else "0", "work_schedule_code": "F",
             "length_of_service_years": "0.5" if i < 45 or a == "CC" else "12.0"}
            for a, n in (("AA", "AGENCY A"), ("BB", "AGENCY B"), ("CC", "AGENCY C")) for i in range(100)])

    (tmp_path / "manifest.json").write_text(json.dumps({"files": files}))
    return tmp_path


def read(path):
    with path.open() as fh:
        return list(csv.DictReader(fh))


def run(raw, tmp_path):
    out = tmp_path / "out"
    build.build(raw=raw, out_dirs=(out,), params=PARAMS)
    return out


def row(rows, **match):
    hits = [r for r in rows if all(r[k] == v for k, v in match.items())]
    assert len(hits) == 1, (match, hits)
    return hits[0]


def test_rates_use_average_september_headcount(raw, tmp_path):
    out = run(raw, tmp_path)
    aa = row(read(out / "agency_year.csv"), agency_code="AA", fiscal_year="2013")
    # 12 months x 2 quits, plus 1 late quit effective Sep 2013. Headcount 100 at both ends.
    assert aa["quits"] == "27"  # includes the DRP-flagged quit and the seasonal quit
    assert aa["retirements"] == "36"
    assert float(aa["quit_rate"]) == 27.0
    assert aa["drp_quits"] == "1"
    assert float(aa["quit_rate_excl_drp"]) == 26.0


def test_core_rate_leaves_out_seasonal_and_temporary_staff(raw, tmp_path):
    out = run(raw, tmp_path)
    aa = row(read(out / "agency_year.csv"), agency_code="AA", fiscal_year="2013")
    # 26 quits by permanent, regular-schedule staff (the seasonal one is left out)
    # over 90 permanent staff at both ends
    assert aa["core_quits"] == "26"
    assert aa["core_avg_headcount"] == "90"
    assert float(aa["core_quit_rate"]) == round(100 * 26 / 90, 2)
    assert aa["incomplete"] == "false"


def test_late_record_counts_in_its_effective_year(raw, tmp_path):
    out = run(raw, tmp_path)
    fy14 = [r for r in read(out / "agency_year.csv") if r["fiscal_year"] == "2014"]
    assert fy14 == []  # no Sep 2014 headcount yet, so no FY2014 rate, and the late record stayed in FY2013


def test_missing_submission_is_a_gap_not_retention(raw, tmp_path):
    out = run(raw, tmp_path)
    gaps = read(out / "coverage_gaps.csv")
    assert [(g["agency_code"], g["file_month"]) for g in gaps] == [("BB", "201303")]


def test_service_bands_cover_permanent_quits(raw, tmp_path):
    out = run(raw, tmp_path)
    aa = {r["service_band"]: r for r in read(out / "service_year.csv")
          if r["fiscal_year"] == "2013" and r["agency_code"] == "AA"}
    # every permanent quit in the fixture has half a year of service. 45 permanent staff are in that band
    assert aa["under 1"]["core_quits"] == "26"
    assert aa["under 1"]["core_avg_headcount"] == "45"
    assert aa["10 to 19"]["core_quits"] == "0"
    every = [r for r in read(out / "service_year.csv") if r["fiscal_year"] == "2013" and r["agency_code"] == "ALL"]
    assert sum(int(r["core_quits"]) for r in every) == sum(
        int(r["core_quits"]) for r in read(out / "agency_year.csv") if r["fiscal_year"] == "2013" and r["incomplete"] == "false")


def test_seasonal_low_month_is_not_a_gap(raw, tmp_path):
    out = run(raw, tmp_path)
    cc = [r for r in read(out / "agency_year.csv") if r["agency_code"] == "CC"]
    assert cc and all(r["incomplete"] == "false" for r in cc)


def test_first_months_get_a_full_baseline(raw, tmp_path):
    out = run(raw, tmp_path)
    months_out = [r["file_month"] for r in read(out / "agency_month.csv") if r["agency_code"] == "AA"]
    assert months_out[0] == "201107"  # baseline-only files from 2010 are not reported
    first = row(read(out / "agency_month.csv"), agency_code="AA", file_month="201107")
    assert first["baseline"] != ""
    bb = row(read(out / "agency_year.csv"), agency_code="BB", fiscal_year="2013")
    assert bb["incomplete"] == "true"
    assert bb["gap_months"] == "1"


def test_incomplete_agency_years_stay_out_of_occupation_and_benchmark(raw, tmp_path):
    out = run(raw, tmp_path)
    occ = row(read(out / "occupation_year.csv"), fiscal_year="2013")
    assert occ["avg_headcount"] == "200"  # AA and CC counted, BB left out
    bench = row(read(out / "benchmark_year.csv"), fiscal_year="2013", series="Federal civilian (OPM, covered agencies)")
    assert float(bench["quit_rate"]) == round(100 * (27 + 11 * 8 + 1) / 200, 2)


def test_drp_exits_are_their_own_segment(raw, tmp_path):
    out = run(raw, tmp_path)
    seg = {r["segment"]: r for r in read(out / "reason_year.csv") if r["fiscal_year"] == "2013"}
    assert seg["DRP-flagged exit"]["separations"] == "1"
    assert seg["Quit"]["separations"] == str(26 + 11 * 8 + 1)  # AA non-DRP quits + CC quits
    assert sum(int(r["separations"]) for r in seg.values()) == 27 + 36 + 11 * 8 + 1


def test_build_output_passes_the_contract(raw, tmp_path):
    out = run(raw, tmp_path)
    assert contract.validate(out) == []
