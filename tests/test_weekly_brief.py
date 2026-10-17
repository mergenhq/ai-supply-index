"""Tests for examples/weekly_brief.py — small fixture files under tmp_path; the published series is only read."""
import hashlib
import importlib.util
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("weekly_brief", KOK / "examples" / "weekly_brief.py")
wb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wb)
ws = wb.weekly_series

T = {34: "2026-08-18", 35: "2026-08-25", 36: "2026-09-01", 37: "2026-09-08", 38: "2026-09-15"}


def row(week, ozet=None, uc="x402_discovery", durum="OK"):
    r = {"zaman_utc": T[week] + "T07:00:00+00:00", "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def x402(n, **extra):
    return {"kaynak_sayisi": n, **extra}


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def entry(b, name="x402_discovery"):
    return next(e for e in b["endpoints"] if e["endpoint"] == name)


class TestChange:
    @pytest.mark.parametrize("now, before, want", [
        (110, 100, {"from": 100, "to": 110, "abs": 10, "pct": 10.0}),
        (90, 100, {"from": 100, "to": 90, "abs": -10, "pct": -10.0}),
        (3, 0, {"from": 0, "to": 3, "abs": 3, "pct": None}),
        (0, 4, {"from": 4, "to": 0, "abs": -4, "pct": -100.0}),
        (763773.64, 902574.56, {"from": 902574.56, "to": 763773.64, "abs": -138800.92, "pct": -15.38}),
    ])
    def test_change(self, now, before, want):
        assert wb.change(now, before) == want

    @pytest.mark.parametrize("now, before", [(None, 1), (1, None), (None, None)])
    def test_missing_side_gives_no_change(self, now, before):
        assert wb.change(now, before) is None


class TestBrief:
    def test_last_week_by_default_with_previous_and_earlier(self):
        rows = [row(w, x402(100 + w)) for w in (34, 35, 36, 37, 38)]
        b = wb.brief(rows, compare=4)
        e = entry(b)
        assert (b["week"], b["previous"], b["earlier"]) == ("2026-W38", "2026-W37", "2026-W34")
        assert e["value"] == 138 and e["vs_previous"]["abs"] == 1 and e["vs_earlier"]["abs"] == 4
        assert e["zaman_utc"] == T[38] + "T07:00:00+00:00" and e["what"] == "resources registered"

    def test_chosen_week(self):
        b = wb.brief([row(w, x402(w)) for w in (34, 35, 36)], week="2026-W35", compare=1)
        assert entry(b)["value"] == 35 and b["earlier"] == "2026-W34"

    def test_gap_week_value_is_missing_and_not_compared(self):
        b = wb.brief([row(34, x402(5)), row(35, x402(6)), row(36, durum="HATA")], compare=2)
        e = entry(b)
        assert e["value"] is None and e["gap"] == "rows present, none usable"
        assert e["vs_previous"] is None and e["vs_earlier"] is None

    def test_change_against_a_gap_week_is_missing(self):
        b = wb.brief([row(34, x402(5)), row(36, x402(7))], compare=2)   # W35 has no rows
        e = entry(b)
        assert e["vs_previous"] is None and e["vs_earlier"] == {"from": 5, "to": 7, "abs": 2, "pct": 40.0}

    def test_earlier_week_before_the_series_is_missing(self):
        b = wb.brief([row(34, x402(5)), row(35, x402(6))], compare=4)
        assert b["earlier"] is None and entry(b)["vs_earlier"] is None

    def test_compare_zero_leaves_it_out(self):
        b = wb.brief([row(34, x402(5)), row(35, x402(6))], compare=0)
        assert b["earlier"] is None and entry(b)["vs_previous"]["abs"] == 1

    def test_unusable_rows_follow_the_weekly_series_rules(self):
        rows = [row(34, x402(5)), row(35, x402(0, olculemedi="schema broken"))]
        e = entry(wb.brief(rows))
        assert e["value"] is None and e["vs_previous"] is None

    def test_shares_from_the_chosen_row(self):
        d = {"n": 3, "p50": 1, "top1_pay": 0.5, "top10_pay": 1.0}
        b = wb.brief([row(34, x402(5, cagri_30g=d, odeyen_30g={"n": 3, "p50": 0}))])
        assert entry(b)["shares"] == [{"field": "cagri_30g", "n": 3, "top1_pay": 0.5, "top10_pay": 1.0},
                                      {"field": "odeyen_30g", "n": 3, "top1_pay": None, "top10_pay": None}]

    def test_endpoint_that_starts_later_is_left_out_of_earlier_weeks(self):
        rows = [row(34, x402(5)), row(35, x402(6)), row(35, {"magaza_toplam_aktor": 9}, uc="apify_store")]
        assert [e["endpoint"] for e in wb.brief(rows, week="2026-W34")["endpoints"]] == ["x402_discovery"]

    def test_unknown_week_is_an_error(self):
        with pytest.raises(ValueError, match="not in the series"):
            wb.brief([row(34, x402(5))], week="2026-W50")


class TestMarkdown:
    def md(self, capsys, tmp_path, rows, *args):
        assert wb.main(["--series", str(series(tmp_path, rows)), *args]) == 0
        return capsys.readouterr().out

    def test_layout(self, tmp_path, capsys):
        d = {"n": 3, "p50": 1, "top1_pay": 0.5, "top10_pay": 1.0}
        out = self.md(capsys, tmp_path, [row(34, x402(100)), row(35, x402(110, cagri_30g=d))], "--compare", "1")
        lines = out.splitlines()
        assert lines[0] == "# AI Supply Index — 2026-W35"
        assert "| endpoint | value | what | vs 2026-W34 | vs 2026-W34 | run |" in lines
        want = "| `x402_discovery` | 110 | resources registered | +10 (+10.00 %) | +10 (+10.00 %) | {}T07:00:00+00:00 |"
        assert want.format(T[35]) in lines
        assert "| `x402_discovery` | `cagri_30g` | 3 | 50.0 % | 100.0 % |" in lines

    def test_gap_and_missing_change_are_written_as_missing_not_zero(self, tmp_path, capsys):
        out = self.md(capsys, tmp_path, [row(34, x402(5)), row(35, durum="HATA")], "--compare", "1")
        assert "| `x402_discovery` | no usable value (rows present, none usable) | resources registered | n/a | n/a |  |" in out
        assert "## Concentration" not in out

    def test_source_line_names_the_file_and_its_hash(self, tmp_path, capsys):
        p = series(tmp_path, [row(34, x402(5))])
        assert wb.main(["--series", str(p)]) == 0
        assert "`s.ndjson` (sha256 %s…)" % hashlib.sha256(p.read_bytes()).hexdigest()[:16] in capsys.readouterr().out

    def test_json(self, tmp_path, capsys):
        b = json.loads(self.md(capsys, tmp_path, [row(34, x402(5)), row(35, x402(7))], "--json"))
        assert b["week"] == "2026-W35" and entry(b)["vs_previous"]["abs"] == 2 and b["source"]["name"] == "s.ndjson"

    def test_errors(self, tmp_path, capsys):
        p = series(tmp_path, [row(34, x402(5))])
        assert wb.main(["--series", str(p), "--week", "2026-W50"]) == 1
        assert wb.main(["--series", str(tmp_path / "yok")]) == 1
        assert wb.main(["--series", str(series(tmp_path, []))]) == 1
        with pytest.raises(SystemExit):
            wb.main(["--series", str(p), "--compare", "-1"])

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            wb.main(["--help"])
        assert "never as 0" in " ".join(capsys.readouterr().out.split())


def test_published_series_brief_matches_the_weekly_values():
    rows = ws.read_rows(KOK / "ai-arz-serisi.ndjson")
    b = wb.brief(rows)
    weekly = {(e["week"], e["endpoint"]): e["value"] for e in ws.weekly(rows)}
    assert b["endpoints"]
    for e in b["endpoints"]:
        assert e["value"] == weekly[(b["week"], e["endpoint"])]
        if e["vs_previous"] is not None:
            assert e["vs_previous"]["from"] == weekly[(b["previous"], e["endpoint"])]
