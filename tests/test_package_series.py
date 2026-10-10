"""Tests for examples/package_series.py — small fixture files under tmp_path; the published series is only read."""
import csv
import importlib.util
import io
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("package_series", KOK / "examples" / "package_series.py")
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)
ws = ps.weekly_series

T = {34: "2026-08-18T07:00:00+00:00", 35: "2026-08-25T07:00:00+00:00", 36: "2026-09-01T07:00:00+00:00"}


def npm(**pkgs):
    return {name.replace("_", "/"): ({"toplam_30g": v, "gun": 30} if not isinstance(v, dict) else v)
            for name, v in pkgs.items()}


def row(week, ozet=None, uc="npm_downloads", durum="OK", stamp=None):
    r = {"zaman_utc": stamp or T[week], "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def table(rows, endpoint="npm_downloads", field=None, only=None):
    return {(e["week"], e["package"]): e for e in ps.package_series(rows, endpoint, field, only)}


class TestValues:
    def test_one_value_per_package_and_week(self):
        t = table([row(34, npm(a=10, b=20)), row(35, npm(a=11, b=22))])
        assert {k: e["value"] for k, e in t.items()} == {
            ("2026-W34", "a"): 10, ("2026-W34", "b"): 20, ("2026-W35", "a"): 11, ("2026-W35", "b"): 22}
        assert t[("2026-W35", "a")]["zaman_utc"] == T[35] and t[("2026-W35", "a")]["field"] == "toplam_30g"

    def test_package_names_with_slashes_are_kept(self):
        t = table([row(34, {"@anthropic-ai/sdk": {"toplam_30g": 5}})])
        assert list(t) == [("2026-W34", "@anthropic-ai/sdk")]

    def test_other_field(self):
        t = table([row(34, npm(a={"toplam_30g": 10, "gun": 31}))], field="gun")
        assert t[("2026-W34", "a")]["value"] == 31 and t[("2026-W34", "a")]["field"] == "gun"

    def test_default_fields(self):
        assert [ps.FIELDS[e][0] for e in ("npm_downloads", "pypi_downloads", "github_repos")] == [
            "toplam_30g", "aynasiz_toplam", "yildiz"]

    def test_last_usable_row_of_the_week_wins(self):
        rows = [row(34, npm(a=1)), row(34, npm(a=2), stamp="2026-08-20T07:00:00+00:00"),
                row(34, durum="HATA", stamp="2026-08-21T07:00:00+00:00")]
        assert table(rows)[("2026-W34", "a")]["value"] == 2

    def test_measured_zero_is_kept(self):
        t = table([row(34, {"o/r": {"yildiz": 0}}, uc="github_repos")], "github_repos")
        assert t[("2026-W34", "o/r")]["value"] == 0 and "gap" not in t[("2026-W34", "o/r")]

    def test_package_filter(self):
        assert {k[1] for k in table([row(34, npm(a=1, b=2, c=3))], only=["b"])} == {"b"}


class TestGaps:
    def test_row_with_a_failed_package_is_missing_for_every_package(self):
        rows = [row(34, npm(a=10, b=20)), row(35, npm(a=11, b={"hata": "HTTPError 429"})), row(36, npm(a=12, b=24))]
        t = table(rows)
        assert t[("2026-W35", "a")]["value"] is None and t[("2026-W35", "b")]["value"] is None
        assert t[("2026-W35", "a")]["gap"] == "rows present, none usable"

    def test_package_olculemedi_makes_the_row_missing(self):
        rows = [row(34, npm(a=10, b={"toplam_30g": 3, "olculemedi": "1 of 30 day records"}))]
        assert table(rows)[("2026-W34", "a")]["value"] is None

    def test_week_without_rows_is_a_gap(self):
        t = table([row(34, npm(a=1)), row(36, npm(a=3))])
        assert t[("2026-W35", "a")] == {"week": "2026-W35", "endpoint": "npm_downloads", "package": "a",
                                        "field": "toplam_30g", "value": None, "zaman_utc": None, "gap": "no rows"}

    def test_package_not_in_the_chosen_row_is_a_gap(self):
        t = table([row(34, npm(a=1, b=2)), row(35, npm(a=3))])
        assert t[("2026-W35", "b")]["gap"] == "package not in this row" and t[("2026-W35", "b")]["zaman_utc"] == T[35]

    def test_non_numeric_field_is_a_gap(self):
        t = table([row(34, npm(a=1)), row(34, {"a": {"toplam_30g": 4}, "b": {"toplam_30g": "x"}},
                                             stamp="2026-08-20T07:00:00+00:00")])
        assert t[("2026-W34", "b")]["gap"] == "no numeric value" and t[("2026-W34", "a")]["value"] == 4


class TestMain:
    def out(self, capsys, tmp_path, rows, *args):
        assert ps.main(["--series", str(series(tmp_path, rows)), *args]) == 0
        return capsys.readouterr().out

    def test_text(self, tmp_path, capsys):
        lines = self.out(capsys, tmp_path, [row(34, npm(a=1500)), row(36, npm(a=1600))],
                         "--endpoint", "npm_downloads").splitlines()
        assert lines[0].split() == ["2026-W34", "a", "1,500", T[34]]
        assert lines[1].split() == ["2026-W35", "a", "GAP", "(no", "rows)"]

    def test_csv_leaves_gaps_empty(self, tmp_path, capsys):
        got = list(csv.reader(io.StringIO(self.out(
            capsys, tmp_path, [row(34, npm(a=1)), row(36, npm(a=3))], "--endpoint", "npm_downloads", "--csv"))))
        assert got[0] == ps.COLUMNS
        assert got[2] == ["2026-W35", "npm_downloads", "a", "toplam_30g", "", "", "no rows"]
        assert got[1][4] == "1"

    def test_json_with_package_and_field(self, tmp_path, capsys):
        rows = [row(34, {"x/y": {"yildiz": 5, "catal": 2}, "p/q": {"yildiz": 1}}, uc="github_repos")]
        lines = self.out(capsys, tmp_path, rows, "--endpoint", "github_repos", "--field", "catal",
                         "--package", "x/y", "--json").splitlines()
        assert [json.loads(x) for x in lines] == [{"week": "2026-W34", "endpoint": "github_repos", "package": "x/y",
                                                   "field": "catal", "value": 2, "zaman_utc": T[34]}]

    def test_field_must_belong_to_the_endpoint(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as e:
            ps.main(["--series", str(series(tmp_path, [])), "--endpoint", "npm_downloads", "--field", "yildiz"])
        assert e.value.code == 2

    def test_endpoint_is_required_and_limited(self, capsys):
        for argv in ([], ["--endpoint", "x402_discovery"]):
            with pytest.raises(SystemExit):
                ps.main(argv)

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert ps.main(["--series", str(tmp_path / "yok"), "--endpoint", "npm_downloads"]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            ps.main(["--help"])
        assert "never as 0" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("endpoint", sorted(ps.FIELDS))
def test_published_series_packages_add_up_to_the_weekly_value(endpoint):
    rows = ws.read_rows(KOK / "ai-arz-serisi.ndjson")
    weekly = {e["week"]: e for e in ws.weekly(rows, [endpoint])}
    per_week = {}
    for e in ps.package_series(rows, endpoint):
        per_week.setdefault(e["week"], []).append(e)
    assert per_week and set(per_week) == set(weekly)
    for week, entries in per_week.items():
        values = [e["value"] for e in entries if e["value"] is not None]
        if weekly[week]["value"] is None:
            assert values == []
        else:
            assert sum(values) == weekly[week]["value"]
