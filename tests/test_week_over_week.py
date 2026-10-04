"""Tests for examples/week_over_week.py — synthetic series under tmp_path; the real series is only read."""
import importlib.util
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("week_over_week", KOK / "examples" / "week_over_week.py")
wow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wow)
ws = wow.weekly_series

# ISO weeks: 2026-08-17..23 is W34, 2026-08-24..30 is W35, 2026-08-31..09-06 is W36
W34, W35, W36 = "2026-W34", "2026-W35", "2026-W36"
T34, T35, T36 = "2026-08-18T07:00:00+00:00", "2026-08-25T07:00:00+00:00", "2026-09-01T07:00:00+00:00"


def row(stamp, uc="x402_discovery", ozet=None, durum="OK"):
    r = {"zaman_utc": stamp, "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def x402(n):
    return {"kaynak_sayisi": n}


def pairs(rows, uc="x402_discovery"):
    return {r["week"]: r for r in wow.changes(ws.weekly(rows)) if r["endpoint"] == uc}


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


class TestChange:
    def test_absolute_and_percentage_change(self):
        p = pairs([row(T34, ozet=x402(200)), row(T35, ozet=x402(250))])
        assert p[W35] == {"endpoint": "x402_discovery", "week": W35, "previous_week": W34,
                          "previous": 200, "value": 250, "change": 50, "change_pct": 25.0}

    def test_decrease_is_negative(self):
        p = pairs([row(T34, ozet=x402(200)), row(T35, ozet=x402(150))])
        assert p[W35]["change"] == -50 and p[W35]["change_pct"] == -25.0

    def test_change_from_a_measured_zero_has_no_percentage(self):
        p = pairs([row(T34, "sherlock_contests", {"acik_yarisma": 0}),
                   row(T35, "sherlock_contests", {"acik_yarisma": 2})], "sherlock_contests")
        assert p[W35]["change"] == 2 and p[W35]["change_pct"] is None and "gap" not in p[W35]

    def test_change_to_a_measured_zero_is_minus_100_percent(self):
        p = pairs([row(T34, "sherlock_contests", {"acik_yarisma": 4}),
                   row(T35, "sherlock_contests", {"acik_yarisma": 0})], "sherlock_contests")
        assert p[W35]["change"] == -4 and p[W35]["change_pct"] == -100.0

    def test_float_change_is_rounded(self):
        p = pairs([row(T34, "defillama_fees_ai_agents", {"ai_total30d": 902574.56}),
                   row(T35, "defillama_fees_ai_agents", {"ai_total30d": 763773.64})], "defillama_fees_ai_agents")
        assert p[W35]["change"] == -138800.92 and p[W35]["change_pct"] == -15.3783

    def test_first_week_has_no_pair(self):
        assert list(pairs([row(T34, ozet=x402(1)), row(T35, ozet=x402(2))])) == [W35]

    def test_uses_the_last_usable_row_of_each_week(self):
        p = pairs([row(T34, ozet=x402(1)), row("2026-08-20T07:00:00+00:00", ozet=x402(10)),
                   row("2026-08-21T07:00:00+00:00", durum="HATA"), row(T35, ozet=x402(15))])
        assert p[W35]["previous"] == 10 and p[W35]["change"] == 5


class TestGaps:
    def test_gap_in_the_later_week_gives_a_gap(self):
        p = pairs([row(T34, ozet=x402(5)), row(T35, durum="HTTP-HATA"), row(T36, ozet=x402(9))])
        assert p[W35]["change"] is None and p[W35]["change_pct"] is None
        assert p[W35]["gap"] == "no usable value in %s" % W35 and p[W35]["previous"] == 5

    def test_gap_in_the_earlier_week_gives_a_gap(self):
        p = pairs([row(T34, ozet=x402(5)), row(T35, durum="HTTP-HATA"), row(T36, ozet=x402(9))])
        assert p[W36]["change"] is None and p[W36]["gap"] == "no usable value in %s" % W35

    def test_gaps_on_both_sides_name_both_weeks(self):
        p = pairs([row(T34, durum="HATA"), row(T35, ozet={"kaynak_sayisi": 1, "olculemedi": "x"}),
                   row(T36, ozet=x402(1))])
        assert p[W35]["gap"] == "no usable value in %s and %s" % (W34, W35)

    def test_week_without_rows_gives_a_gap_not_a_change_from_zero(self):
        p = pairs([row(T34, ozet=x402(5)), row(T36, ozet=x402(9))])
        assert p[W35]["change"] is None and p[W36]["change"] is None
        assert p[W35]["gap"] == p[W36]["gap"] == "no usable value in %s" % W35

    def test_unmeasurable_zero_is_a_gap_not_a_change(self):
        p = pairs([row(T34, "sherlock_contests", {"acik_yarisma": 3}),
                   row(T35, "sherlock_contests", {"acik_yarisma": 0, "olculemedi": "schema broken"})],
                  "sherlock_contests")
        assert p[W35]["change"] is None and "gap" in p[W35]

    def test_failed_package_is_a_gap(self):
        p = pairs([row(T34, "npm_downloads", {"a": {"toplam_30g": 10}}),
                   row(T35, "npm_downloads", {"a": {"toplam_30g": 12}, "b": {"hata": "429"}})], "npm_downloads")
        assert p[W35]["change"] is None


class TestMain:
    def test_table(self, tmp_path, capsys):
        p = series(tmp_path, [row(T34, ozet=x402(15000)), row(T35, ozet=x402(15300)),
                              row(T36, durum="HATA")])
        assert wow.main(["--series", str(p)]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[0].split() == [W35, "x402_discovery", "+300", "+2.00", "%", "(15,000", "->", "15,300)"]
        assert out[1] == "%s  %-28s  GAP (no usable value in %s)" % (W36, "x402_discovery", W36)

    def test_table_marks_a_change_from_zero(self, tmp_path, capsys):
        p = series(tmp_path, [row(T34, "sherlock_contests", {"acik_yarisma": 0}),
                              row(T35, "sherlock_contests", {"acik_yarisma": 1})])
        assert wow.main(["--series", str(p)]) == 0
        assert "n/a (from 0)" in capsys.readouterr().out

    def test_json_and_endpoint_filter(self, tmp_path, capsys):
        p = series(tmp_path, [row(T34, ozet=x402(1)), row(T35, ozet=x402(2)),
                              row(T34, "apify_store", {"magaza_toplam_aktor": 10}),
                              row(T35, "apify_store", {"magaza_toplam_aktor": 11})])
        assert wow.main(["--series", str(p), "--endpoint", "apify_store", "--json"]) == 0
        lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
        assert lines == [{"endpoint": "apify_store", "week": W35, "previous_week": W34, "previous": 10,
                          "value": 11, "change": 1, "change_pct": 10.0}]

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert wow.main(["--series", str(tmp_path / "yok.ndjson")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_line_that_is_not_json_exits_with_an_error(self, tmp_path, capsys):
        p = tmp_path / "s.ndjson"
        p.write_text("{bozuk\n", encoding="utf-8")
        assert wow.main(["--series", str(p)]) == 1

    def test_empty_series_prints_nothing(self, tmp_path, capsys):
        assert wow.main(["--series", str(series(tmp_path, []))]) == 0
        assert capsys.readouterr().out == ""

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            wow.main(["--help"])
        assert "never as a change from or to 0" in " ".join(capsys.readouterr().out.split())


def test_real_series_pairs_match_the_weekly_values():
    entries = ws.weekly(ws.read_rows(KOK / "ai-arz-serisi.ndjson"))
    val = {(e["week"], e["endpoint"]): e["value"] for e in entries}
    rows = wow.changes(entries)
    assert rows
    for r in rows:
        assert val[(r["week"], r["endpoint"])] == r["value"]
        assert val[(r["previous_week"], r["endpoint"])] == r["previous"]
        if r["value"] is None or r["previous"] is None:
            assert r["change"] is None and "gap" in r
        else:
            assert r["change"] == pytest.approx(r["value"] - r["previous"], abs=1e-4)
