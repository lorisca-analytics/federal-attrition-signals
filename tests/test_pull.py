import io
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from fas import pull


def parquet_bytes(tag: str) -> bytes:
    buf = io.BytesIO()
    pq.write_table(pa.table({"tag": [tag]}), buf)
    return buf.getvalue()


class FakeOPM:
    """Serves a file listing and Parquet files. Can be told to fail on a given URL."""

    def __init__(self, months, versions=None, fail_on=None):
        self.versions = versions or {}
        self.months = months
        self.fail_on = fail_on
        self.calls = []

    def listing(self, dataset):
        return [{"year": ym[:4], "month": ym[4:], "version": self.versions.get(ym, 1),
                 "current": True, "publishDate": "2026-11-04"} for ym in self.months]

    def __call__(self, url, body=None):
        self.calls.append(url)
        if self.fail_on and self.fail_on in url:
            raise OSError("connection dropped")
        if url.endswith("/separations"):
            return json.dumps(self.listing("separations")).encode()
        if url.endswith("/employment"):
            return json.dumps(self.listing("employment")).encode()
        return parquet_bytes(url)

    def downloads(self):
        return [c for c in self.calls if c.endswith("/download")]


MONTHS = ["202606", "202607", "202608", "202609"]


def test_second_run_downloads_nothing(tmp_path):
    fake = FakeOPM(MONTHS)
    first = pull.pull_opm(tmp_path, fake, log=lambda *_: None)
    assert first["downloaded"] == 4 + 1  # four separations months, one September headcount
    fake.calls.clear()
    second = pull.pull_opm(tmp_path, fake, log=lambda *_: None)
    assert second["downloaded"] == 0
    assert fake.downloads() == []


def test_stopped_run_resumes_where_it_stopped(tmp_path):
    broken = FakeOPM(MONTHS, fail_on="separations/2026/08")
    with pytest.raises(OSError):
        pull.pull_opm(tmp_path, broken, log=lambda *_: None)
    done = json.loads((tmp_path / "manifest.json").read_text())["files"]
    assert set(done) == {"separations/2026/06", "separations/2026/07"}
    assert not list(tmp_path.glob("separations_202608*"))

    fixed = FakeOPM(MONTHS)
    stats = pull.pull_opm(tmp_path, fixed, log=lambda *_: None)
    pulled = [u for u in fixed.downloads()]
    assert stats["downloaded"] == 3
    assert not any("2026/06" in u or "2026/07" in u for u in pulled)


def test_new_version_is_pulled_and_old_one_kept(tmp_path):
    pull.pull_opm(tmp_path, FakeOPM(MONTHS), log=lambda *_: None)
    revised = FakeOPM(MONTHS, versions={"202607": 2})
    stats = pull.pull_opm(tmp_path, revised, log=lambda *_: None)
    assert stats == {"downloaded": 1, "skipped": 4, "revised": 1}
    rec = json.loads((tmp_path / "manifest.json").read_text())["files"]["separations/2026/07"]
    assert rec["version"] == 2
    assert rec["superseded"] == [{"version": 1, "file": "separations_202607_v1.parquet"}]
    assert (tmp_path / "separations_202607_v1.parquet").exists()
    assert (tmp_path / "separations_202607_v2.parquet").exists()


def test_changed_file_on_disk_is_pulled_again(tmp_path):
    pull.pull_opm(tmp_path, FakeOPM(MONTHS), log=lambda *_: None)
    (tmp_path / "separations_202606_v1.parquet").write_bytes(b"PAR1 damaged")
    stats = pull.pull_opm(tmp_path, FakeOPM(MONTHS), log=lambda *_: None)
    assert stats["downloaded"] == 1


def test_non_parquet_download_is_refused(tmp_path):
    def html_instead(url, body=None):
        if url.endswith("/separations") or url.endswith("/employment"):
            return json.dumps([{"year": "2026", "month": "09", "version": 1, "current": True}]).encode()
        return b"<html>maintenance</html>"

    with pytest.raises(ValueError):
        pull.pull_opm(tmp_path, html_instead, log=lambda *_: None)
    assert not (tmp_path / "separations_202609_v1.parquet").exists()
    assert not list(tmp_path.glob("*.part"))
    assert not (tmp_path / "manifest.json").exists()


def test_only_september_headcount_and_months_from_jul_2011():
    listing = [{"year": y, "month": m, "version": 1, "current": True}
               for y, m in [("2011", "06"), ("2011", "07"), ("2011", "09"), ("2012", "03")]]
    sep = pull.wanted_files("separations", listing)
    emp = pull.wanted_files("employment", listing)
    assert [w.year + w.month for w in sep] == ["201107", "201109", "201203"]
    assert [w.year + w.month for w in emp] == ["201109"]


def test_superseded_versions_in_listing_are_ignored():
    listing = [{"year": "2026", "month": "07", "version": 1, "current": False},
               {"year": "2026", "month": "07", "version": 2, "current": True}]
    assert [w.version for w in pull.wanted_files("separations", listing)] == [2]
