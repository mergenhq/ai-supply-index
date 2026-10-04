"""Tests for examples/concentration.py — small fixture files under tmp_path; the published series is only read."""
import csv
import importlib.util
import io
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("concentration", KOK / "examples" / "concentration.py")
cn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cn)
ws = cn.weekly_series

T = {34: "2026-08-18T07:00:00+00:00", 35: "2026-08-25T07:00:00+00:00", 36: "2026-09-01T07:00:00+00:00"}


def dist(n, p50, p90, top1=None, top10=None):
    d = {"n": n, "toplam": 1.0, "sifir_sayisi": 0, "p10": 0, "p50": p50, "p90": p90, "maks": p90,
         "histogram": {"<1": 0}}
    if top1 is not None:
        d.update(top1_pay=top1, top10_pay=top10)
    return d


def x402(cagri=None, odeyen=None, kaynak=100, **extra):
    o = {"kaynak_sayisi": kaynak, **extra}
    if cagri is not None:
        o["cagri_30g"] = cagri
    if odeyen is not None:
        o["odeyen_30g"] = odeyen
    return o


def row(week, ozet=None, uc="x402_discovery", durum="OK", stamp=None):
    r = {"zaman_utc": stamp or T[week], "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def entries(rows, endpoints=None):
    return {(e["week"], e["endpoint"], e["field"]): e for e in cn.concentration(rows, endpoints)}


class TestFields:
    def test_distribution_fields_are_objects_with_n_and_p50(self):
        rows = [row(34, x402(dist(10, 1, 7, .1, .5), {"n": 0}, top10_cagri=[{"cagri": 1}])),
                row(34, {"omur_boyu_odeme": dist(5, 400, 9000, .2, .6), "arastirmaci_sayisi": 5},
                    uc="sherlock_leaderboard")]
        assert cn.distribution_fields(rows) == {"x402_discovery": ["cagri_30g"],
                                                "sherlock_leaderboard": ["omur_boyu_odeme"]}

    def test_field_that_is_empty_in_every_row_is_not_listed(self):
        assert cn.distribution_fields([row(34, x402({"n": 0}))]) == {}

    def test_field_seen_in_any_row_is_listed(self):
        rows = [row(34, x402({"n": 0}, dist(3, 1, 2, .5, 1.0))), row(35, x402(dist(4, 1, 3, .4, 1.0)))]
        assert cn.distribution_fields(rows)["x402_discovery"] == ["cagri_30g", "odeyen_30g"]


class TestValues:
    def test_stats_come_from_the_chosen_row(self):
        e = entries([row(34, x402(dist(15073, 1, 7, .157, .4946)))])[("2026-W34", "x402_discovery", "cagri_30g")]
        assert e == {"week": "2026-W34", "endpoint": "x402_discovery", "field": "cagri_30g", "n": 15073,
                     "p50": 1, "p90": 7, "top1_pay": .157, "top10_pay": .4946, "zaman_utc": T[34]}

    def test_last_usable_row_of_the_week_wins(self):
        rows = [row(34, x402(dist(10, 1, 7, .1, .5))),
                row(34, x402(dist(20, 2, 8, .2, .6)), stamp="2026-08-20T07:00:00+00:00"),
                row(34, durum="HATA", stamp="2026-08-21T07:00:00+00:00"),
                row(34, x402(dist(30, 3, 9, .3, .7), olculemedi="page cap"), stamp="2026-08-22T07:00:00+00:00")]
        e = entries(rows)[("2026-W34", "x402_discovery", "cagri_30g")]
        assert e["n"] == 20 and e["zaman_utc"] == "2026-08-20T07:00:00+00:00"

    def test_top_shares_absent_when_total_is_zero_are_empty_not_zero(self):
        e = entries([row(34, x402(dist(5, 0, 0)))])[("2026-W34", "x402_discovery", "cagri_30g")]
        assert e["n"] == 5 and e["p50"] == 0 and e["top1_pay"] is None and e["top10_pay"] is None
        assert "gap" not in e

    def test_empty_distribution_has_n_zero_and_empty_stats(self):
        rows = [row(34, x402({"n": 0})), row(35, x402(dist(1, 1, 1, 1.0, 1.0)))]
        e = entries(rows)[("2026-W34", "x402_discovery", "cagri_30g")]
        assert e["n"] == 0 and [e[s] for s in ("p50", "p90", "top1_pay", "top10_pay")] == [None] * 4
        assert "gap" not in e


class TestGaps:
    def test_week_without_rows_is_a_gap(self):
        rows = [row(34, x402(dist(1, 1, 1, 1.0, 1.0))), row(36, x402(dist(2, 1, 1, .5, 1.0)))]
        e = entries(rows)[("2026-W35", "x402_discovery", "cagri_30g")]
        assert e["gap"] == "no rows" and e["n"] is None and e["zaman_utc"] is None

    def test_week_with_only_unusable_rows_is_a_gap(self):
        rows = [row(34, x402(dist(1, 1, 1, 1.0, 1.0))), row(35, durum="HTTP-HATA"),
                row(35, x402(dist(9, 9, 9, .1, .9), olculemedi="x"), stamp="2026-08-26T07:00:00+00:00")]
        e = entries(rows)[("2026-W35", "x402_discovery", "cagri_30g")]
        assert e["gap"] == "rows present, none usable" and e["n"] is None

    def test_field_missing_from_the_chosen_row_is_a_gap(self):
        rows = [row(34, x402(dist(1, 1, 1, 1.0, 1.0), dist(1, 1, 1, 1.0, 1.0))), row(35, x402(dist(2, 1, 1, .5, 1.0)))]
        e = entries(rows)[("2026-W35", "x402_discovery", "odeyen_30g")]
        assert e["gap"] == "field not in this row" and e["zaman_utc"] == T[35] and e["n"] is None


class TestFilterAndOrder:
    def test_endpoint_filter(self):
        rows = [row(34, x402(dist(1, 1, 1, 1.0, 1.0))),
                row(34, {"omur_boyu_odeme": dist(5, 1, 2, .2, .6), "arastirmaci_sayisi": 5}, uc="sherlock_leaderboard")]
        assert {k[1] for k in entries(rows, ["sherlock_leaderboard"])} == {"sherlock_leaderboard"}

    def test_endpoints_without_distributions_are_not_listed(self):
        rows = [row(34, {"a": {"toplam_30g": 5}}, uc="npm_downloads"), row(34, x402(dist(1, 1, 1, 1.0, 1.0)))]
        assert {k[1] for k in entries(rows)} == {"x402_discovery"}

    def test_sorted_by_week_endpoint_field(self):
        rows = [row(35, x402(dist(1, 1, 1, 1.0, 1.0), dist(1, 1, 1, 1.0, 1.0))),
                row(34, x402(dist(1, 1, 1, 1.0, 1.0), dist(1, 1, 1, 1.0, 1.0)))]
        keys = [(e["week"], e["field"]) for e in cn.concentration(rows)]
        assert keys == sorted(keys) and len(keys) == 4


class TestMain:
    def out(self, capsys, tmp_path, rows, *args):
        assert cn.main(["--series", str(series(tmp_path, rows)), *args]) == 0
        return capsys.readouterr().out

    def test_csv_leaves_missing_values_empty(self, tmp_path, capsys):
        rows = [row(34, x402(dist(5, 0, 0))), row(36, x402(dist(7, 1, 2, .5, 1.0)))]
        got = list(csv.reader(io.StringIO(self.out(capsys, tmp_path, rows, "--csv"))))
        assert got[0] == cn.COLUMNS
        assert got[1] == ["2026-W34", "x402_discovery", "cagri_30g", "5", "0", "0", "", "", T[34], ""]
        assert got[2] == ["2026-W35", "x402_discovery", "cagri_30g", "", "", "", "", "", "", "no rows"]
        assert got[3][3:8] == ["7", "1", "2", "0.5", "1.0"]

    def test_json(self, tmp_path, capsys):
        lines = self.out(capsys, tmp_path, [row(34, x402(dist(5, 1, 2, .5, 1.0)))], "--json").splitlines()
        assert json.loads(lines[0])["top1_pay"] == .5 and len(lines) == 1

    def test_text_shows_gap_and_empty_shares(self, tmp_path, capsys):
        rows = [row(34, x402(dist(5, 0, 0))), row(36, x402(dist(7, 1, 2, .5, 1.0)))]
        lines = self.out(capsys, tmp_path, rows).splitlines()
        assert lines[0].split()[:3] == ["week", "endpoint", "field"]
        assert lines[1].split() == ["2026-W34", "x402_discovery", "cagri_30g", "5", "0", "0"]
        assert "GAP (no rows)" in lines[2]
        assert lines[3].split()[-2:] == ["0.5000", "1.0000"]

    def test_csv_and_json_together_are_rejected(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as e:
            cn.main(["--series", str(series(tmp_path, [])), "--csv", "--json"])
        assert e.value.code == 2

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert cn.main(["--series", str(tmp_path / "yok.ndjson")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            cn.main(["--help"])
        assert "never 0" in " ".join(capsys.readouterr().out.split())


def test_published_series_values_match_the_chosen_rows():
    rows = ws.read_rows(KOK / "ai-arz-serisi.ndjson")
    by_key = {(r["zaman_utc"], r["uc"]): r for r in rows}
    got = cn.concentration(rows)
    assert {e["field"] for e in got} >= {"cagri_30g", "odeyen_30g", "omur_boyu_odeme", "indirme_dagilimi"}
    for e in got:
        if e.get("gap"):
            assert all(e[s] is None for s in cn.STATS)
            continue
        d = by_key[(e["zaman_utc"], e["endpoint"])]["ozet"][e["field"]]
        for s in cn.STATS:
            assert e[s] == d.get(s)
