"""Tests for examples/runs.py — small fixture files under tmp_path; the published series is only read."""
import csv
import importlib.util
import io
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("runs", KOK / "examples" / "runs.py")
rn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rn)
ws = rn.weekly_series

A, B, C = "2026-08-18T07:00:00+00:00", "2026-08-20T07:00:00+00:00", "2026-08-25T07:00:00+00:00"


def row(stamp, uc="x402_discovery", ozet=None, durum="OK", **extra):
    r = {"zaman_utc": stamp, "uc": uc, "durum": durum, "surum": "0.3", **extra}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def x402(n=5, **extra):
    return {"kaynak_sayisi": n, **extra}


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


class TestWhyUnusable:
    @pytest.mark.parametrize("r, reason", [
        (row(A, ozet=x402()), None),
        (row(A, durum="HATA"), "durum HATA"),
        (row(A, durum="HTTP-HATA"), "durum HTTP-HATA"),
        (row(A, ozet=None), "no summary"),
        (row(A, ozet=x402(olculemedi="page cap reached")), "olculemedi: page cap reached"),
        (row(A, "npm_downloads", {"a": {"toplam_30g": 1}, "b": {"hata": "429"}}), "package b: hata"),
        (row(A, "npm_downloads", {"a": {"toplam_30g": 1, "olculemedi": "x"}}), "package a: olculemedi"),
        (row(A, ozet={"resource_count": 5}), "no readable value"),
        (row(A, "sherlock_contests", {"acik_yarisma": 0}), None),
    ])
    def test_reason(self, r, reason):
        assert rn.why_unusable(r) == reason

    def test_reason_agrees_with_weekly_series(self):
        rows = [row(A, ozet=x402()), row(A, durum="HATA"), row(A, ozet=x402(olculemedi="x")),
                row(A, "npm_downloads", {"b": {"hata": "429"}}), row(A, ozet={"resource_count": 5})]
        for r in rows:
            assert (rn.why_unusable(r) is None) == (ws.value(r) is not None)


class TestRuns:
    def test_counts_per_run(self):
        rows = [row(A, ozet=x402()), row(A, "apify_store", durum="HATA"),
                row(A, "npm_downloads", {"p": {"toplam_30g": 3}, "q": {"hata": "429"}})]
        (r,) = rn.runs(rows)
        assert (r["zaman_utc"], r["week"], r["rows"], r["ok"], r["usable"]) == (A, "2026-W34", 3, 2, 1)
        assert r["unusable"] == [{"endpoint": "apify_store", "reason": "durum HATA"},
                                 {"endpoint": "npm_downloads", "reason": "package q: hata"}]

    def test_picked_follows_weekly_series(self):
        rows = [row(A, ozet=x402(1)), row(A, "apify_store", {"magaza_toplam_aktor": 5}),
                row(B, ozet=x402(2)), row(B, "apify_store", durum="HATA"), row(C, ozet=x402(3))]
        got = {r["zaman_utc"]: r["picked"] for r in rn.runs(rows)}
        assert got == {A: ["apify_store"], B: ["x402_discovery"], C: ["x402_discovery"]}

    def test_every_picked_endpoint_matches_the_weekly_value(self):
        rows = [row(A, ozet=x402(1)), row(B, ozet=x402(olculemedi="x")), row(C, durum="HATA")]
        got = {r["zaman_utc"]: r["picked"] for r in rn.runs(rows)}
        assert got == {A: ["x402_discovery"], B: [], C: []}

    def test_runs_are_sorted_by_time(self):
        rows = [row(C, ozet=x402()), row(A, ozet=x402())]
        assert [r["zaman_utc"] for r in rn.runs(rows)] == [A, C]

    def test_versions_and_collectors(self):
        rows = [row(A, ozet=x402(), toplayici="c2"), row(A, "apify_store", {"magaza_toplam_aktor": 1}, surum="0.4"),
                {"zaman_utc": B, "uc": "x402_discovery", "durum": "OK", "ozet": x402()}]
        got = {r["zaman_utc"]: (r["versions"], r["collectors"]) for r in rn.runs(rows)}
        assert got == {A: (["0.3", "0.4"], ["c2"]), B: ([], [])}

    def test_rows_without_stamp_or_endpoint_are_skipped(self):
        assert rn.runs([{"uc": "x402_discovery"}, {"zaman_utc": A}]) == []


class TestMain:
    def out(self, capsys, tmp_path, rows, *args):
        assert rn.main(["--series", str(series(tmp_path, rows)), *args]) == 0
        return capsys.readouterr().out

    def test_text(self, tmp_path, capsys):
        lines = self.out(capsys, tmp_path, [row(A, ozet=x402()), row(A, "apify_store", durum="HATA")]).splitlines()
        assert lines[0].split() == [A, "2026-W34", "rows", "2", "ok", "1", "usable", "1", "picked", "1",
                                    "version", "0.3"]
        assert lines[1].split() == ["apify_store", "durum", "HATA"]

    def test_week_filter(self, tmp_path, capsys):
        out = self.out(capsys, tmp_path, [row(A, ozet=x402()), row(C, ozet=x402())], "--week", "2026-W35")
        assert out.splitlines()[0].startswith(C) and len(out.splitlines()) == 1

    def test_csv(self, tmp_path, capsys):
        got = list(csv.reader(io.StringIO(self.out(
            capsys, tmp_path, [row(A, ozet=x402(), toplayici="c1"), row(A, "apify_store", durum="HATA")], "--csv"))))
        assert got == [rn.COLUMNS, [A, "2026-W34", "2", "1", "1", "x402_discovery", "0.3", "c1", "apify_store=durum HATA"]]

    def test_json(self, tmp_path, capsys):
        (line,) = self.out(capsys, tmp_path, [row(A, ozet=x402())], "--json").splitlines()
        assert json.loads(line)["picked"] == ["x402_discovery"]

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert rn.main(["--series", str(tmp_path / "yok")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            rn.main(["--help"])
        assert "why each unusable row is unusable" in " ".join(capsys.readouterr().out.split())


def test_published_series_runs_account_for_every_row_and_weekly_value():
    rows = ws.read_rows(KOK / "ai-arz-serisi.ndjson")
    got = rn.runs(rows)
    assert sum(r["rows"] for r in got) == len(rows)
    assert all(r["usable"] + len(r["unusable"]) == r["rows"] for r in got)
    picked = sorted((r["week"], uc) for r in got for uc in r["picked"])
    weekly = sorted((e["week"], e["endpoint"]) for e in ws.weekly(rows) if e["value"] is not None)
    assert picked == weekly
