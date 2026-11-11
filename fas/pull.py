"""Pull OPM workforce files and BLS quits series into data/raw.

The pull is built to be stopped and run again:
- every finished file is recorded in data/raw/manifest.json with its version and checksum
- a file is written to <name>.part first and renamed only when complete,
  so a stopped run never leaves a half file that looks finished
- a second run downloads nothing that is already there
- when OPM publishes a new version of a month, the new version is pulled
  and the old file is kept, so the two can be compared

Usage:
    python -m fas.pull            # everything the analysis needs
    python -m fas.pull --dry-run  # show what would be downloaded
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

OPM = "https://data.opm.gov/api/v1/files"
BLS = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
UA = "federal-attrition-signals/1.0 (public data analysis)"

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# Headcount is monthly from Jul 2011. Before that OPM only has quarterly snapshots.
FIRST_MONTH = "201107"
# Separations start 12 months earlier, only so the coverage check has a full year of
# history for the first months of the window. They are not counted in any rate.
FIRST_SEPARATIONS_MONTH = "201007"
# One headcount snapshot per fiscal year end (September) is enough for annual rates.
# Monthly headcount would be about 12.6 GB, see DECISIONS.md.
EMPLOYMENT_MONTHS = {"09"}

# BLS JOLTS quits rate (QUR) and total separations rate (TSR), seasonally adjusted.
JOLTS_INDUSTRIES = {
    "000000": "Total nonfarm",
    "910000": "Federal",
    "920000": "State and local",
    "440000": "Retail trade",
    "620000": "Health care and social assistance",
    "700000": "Leisure and hospitality",
}
JOLTS_FIRST_YEAR = 2011

Fetch = Callable[[str, bytes | None], bytes]


def http_fetch(url: str, body: bytes | None = None, tries: int = 4) -> bytes:
    headers = {"User-Agent": UA}
    if body is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.read()
        except OSError:
            if attempt == tries:
                raise
            time.sleep(2 ** attempt)  # 2, 4, 8 seconds
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class Wanted:
    dataset: str
    year: str
    month: str
    version: int
    publish_date: str

    @property
    def key(self) -> str:
        return f"{self.dataset}/{self.year}/{self.month}"

    @property
    def filename(self) -> str:
        return f"{self.dataset}_{self.year}{self.month}_v{self.version}.parquet"

    @property
    def url(self) -> str:
        return f"{OPM}/{self.dataset}/{self.year}/{self.month}/{self.version}/download"


class Manifest:
    """What is on disk, keyed by dataset/year/month. Saved after every file."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"files": {}, "jolts": {}}

    def save(self) -> None:
        tmp = self.path.with_suffix(".json.part")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True))
        os.replace(tmp, self.path)  # atomic on the same disk

    def has(self, w: Wanted, raw: Path) -> bool:
        rec = self.data["files"].get(w.key)
        if not rec or rec["version"] != w.version:
            return False
        f = raw / rec["file"]
        return f.exists() and sha256(f) == rec["sha256"]

    def record(self, w: Wanted, f: Path) -> None:
        old = self.data["files"].get(w.key)
        rec = {
            "version": w.version,
            "file": f.name,
            "sha256": sha256(f),
            "bytes": f.stat().st_size,
            "publish_date": w.publish_date,
            "pulled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "superseded": [],
        }
        if old:
            rec["superseded"] = old.get("superseded", []) + (
                [{"version": old["version"], "file": old["file"]}] if old["version"] != w.version else []
            )
        self.data["files"][w.key] = rec


def sha256(f: Path) -> str:
    h = hashlib.sha256()
    with f.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wanted_files(dataset: str, listing: list[dict]) -> list[Wanted]:
    out = []
    for x in listing:
        if not x.get("current"):
            continue
        first = FIRST_SEPARATIONS_MONTH if dataset == "separations" else FIRST_MONTH
        if x["year"] + x["month"] < first:
            continue
        if dataset == "employment" and x["month"] not in EMPLOYMENT_MONTHS:
            continue
        out.append(Wanted(dataset, x["year"], x["month"], int(x["version"]), x.get("publishDate", "")))
    return sorted(out, key=lambda w: (w.year, w.month))


def latest_employment(listing: list[dict]) -> list[Wanted]:
    """Also keep the newest month, so the current fiscal year has an end point."""
    cur = [x for x in listing if x.get("current")]
    if not cur:
        return []
    x = max(cur, key=lambda r: r["year"] + r["month"])
    return [Wanted("employment", x["year"], x["month"], int(x["version"]), x.get("publishDate", ""))]


def download(w: Wanted, raw: Path, fetch: Fetch) -> Path:
    final = raw / w.filename
    part = raw / (w.filename + ".part")
    part.write_bytes(fetch(w.url, None))
    if not part.read_bytes()[:4] == b"PAR1":
        part.unlink()
        raise ValueError(f"{w.key} v{w.version}: download is not a Parquet file")
    os.replace(part, final)
    return final


def pull_opm(raw: Path, fetch: Fetch, dry_run: bool = False, log=print) -> dict:
    raw.mkdir(parents=True, exist_ok=True)
    m = Manifest(raw / "manifest.json")
    stats = {"downloaded": 0, "skipped": 0, "revised": 0}
    for dataset in ("separations", "employment"):
        listing = json.loads(fetch(f"{OPM}/{dataset}", None))
        todo = wanted_files(dataset, listing)
        if dataset == "employment":
            todo += [w for w in latest_employment(listing) if w.month not in EMPLOYMENT_MONTHS]
        for w in todo:
            if m.has(w, raw):
                stats["skipped"] += 1
                continue
            revised = w.key in m.data["files"]
            log(f"{'would pull' if dry_run else 'pulling'} {w.key} v{w.version}{' (new version)' if revised else ''}")
            if dry_run:
                continue
            f = download(w, raw, fetch)
            m.record(w, f)
            m.save()
            stats["downloaded"] += 1
            stats["revised"] += int(revised)
    return stats


def pull_jolts(raw: Path, fetch: Fetch, last_year: int, log=print) -> int:
    """BLS allows 10 years per keyless request, so the range is split."""
    raw.mkdir(parents=True, exist_ok=True)
    series = [f"JTS{code}000000000{el}R" for code in JOLTS_INDUSTRIES for el in ("QU", "TS")]
    rows = []
    start = JOLTS_FIRST_YEAR
    while start <= last_year:
        end = min(start + 9, last_year)
        body = json.dumps({"seriesid": series, "startyear": str(start), "endyear": str(end)}).encode()
        resp = json.loads(fetch(BLS, body))
        if resp.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS request failed: {resp.get('message')}")
        for s in resp["Results"]["series"]:
            sid = s["seriesID"]
            for d in s["data"]:
                if not d["period"].startswith("M") or d["period"] == "M13":
                    continue
                rows.append({
                    "series_id": sid,
                    "industry_code": sid[3:9],
                    "industry": JOLTS_INDUSTRIES[sid[3:9]],
                    "measure": {"QU": "quits", "TS": "total_separations"}[sid[18:20]],
                    "year": int(d["year"]),
                    "month": int(d["period"][1:]),
                    "rate": float(d["value"]),
                    "preliminary": any(f.get("code") == "P" for f in d.get("footnotes", []) if f),
                })
        start = end + 1
    rows.sort(key=lambda r: (r["series_id"], r["year"], r["month"]))
    out = raw / "jolts.json"
    tmp = out.with_suffix(".json.part")
    tmp.write_text(json.dumps(rows))
    os.replace(tmp, out)
    log(f"jolts: {len(rows)} monthly values")
    return len(rows)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-jolts", action="store_true")
    a = p.parse_args(argv)
    stats = pull_opm(RAW, http_fetch, dry_run=a.dry_run)
    print(f"OPM: {stats}")
    if not a.dry_run and not a.skip_jolts:
        pull_jolts(RAW, http_fetch, last_year=time.gmtime().tm_year)


if __name__ == "__main__":
    main()
