"""Tests for examples/endpoint_summary.py — synthetic series under tmp_path; the real series is only read."""
import csv
import importlib.util
import io
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("endpoint_summary", KOK / "examples" / "endpoint_summary.py")
es = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(es)
ws = es.weekly_series

# ISO weeks 2026-W34 .. W37 start on these Mondays; each stamp is the Tuesday of that week
T = {34: "2026-08-18T07:00:00+00:00", 35: "2026-08-25T07:00:00+00:00",
     36: "2026-09-01T07:00:00+00:00", 37: "2026-09-08T07:00:00+00:00"}


def row(week, uc="x402_discovery", ozet=None, durum="OK", stamp=None):
    r = {"zaman_utc": stamp or T[week], "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def x402(n):
    return {"kaynak_sayisi": n}


def summary(rows, uc="x402_discovery"):
    return {s["endpoint"]: s for s in es.summarise(ws.weekly(rows))}[uc]


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


class TestSummarise:
    def test_continuous_weeks(self):
        s = summary([row(34, ozet=x402(1)), row(35, ozet=x402(2)), row(36, ozet=x402(3))])
        assert s == {"endpoint": "x402_discovery", "first_week": "2026-W34", "last_week": "2026-W36",
                     "usable_weeks": 3, "gap_weeks": 0, "latest_value": 3, "latest_zaman_utc": T[36]}

    def test_gap_weeks_between_first_and_last_are_counted(self):
        s = summary([row(34, ozet=x402(1)), row(35, durum="HATA"), row(37, ozet=x402(4))])
        assert s["usable_weeks"] == 2 and s["gap_weeks"] == 2      # W35 unusable, W36 no rows

    def test_trailing_gap_weeks_are_outside_the_count(self):
        rows = [row(34, ozet=x402(1)), row(35, ozet=x402(2)),
                row(37, "apify_store", {"magaza_toplam_aktor": 9})]  # series runs to W37
        s = summary(rows)
        assert s["last_week"] == "2026-W35" and s["gap_weeks"] == 0 and s["latest_value"] == 2

    def test_leading_unusable_weeks_are_outside_the_count(self):
        s = summary([row(34, durum="HATA"), row(35, ozet=x402(2)), row(36, ozet=x402(3))])
        assert s["first_week"] == "2026-W35" and s["gap_weeks"] == 0 and s["usable_weeks"] == 2

    def test_latest_value_comes_from_the_last_usable_row(self):
        rows = [row(34, ozet=x402(1)), row(35, ozet=x402(7), stamp="2026-08-26T07:00:00+00:00"),
                row(35, ozet=x402(5)), row(35, durum="HTTP-HATA", stamp="2026-08-27T07:00:00+00:00")]
        s = summary(rows)
        assert s["latest_value"] == 7 and s["latest_zaman_utc"] == "2026-08-26T07:00:00+00:00"

    def test_endpoint_without_usable_value(self):
        s = summary([row(34, "sherlock_contests", {"acik_yarisma": 0, "olculemedi": "schema broken"}),
                     row(35, ozet=x402(1))], "sherlock_contests")
        assert s == {"endpoint": "sherlock_contests", "first_week": None, "last_week": None,
                     "usable_weeks": 0, "gap_weeks": 0, "latest_value": None, "latest_zaman_utc": None}

    def test_measured_zero_is_a_usable_value(self):
        s = summary([row(34, "sherlock_contests", {"acik_yarisma": 0})], "sherlock_contests")
        assert s["usable_weeks"] == 1 and s["latest_value"] == 0

    def test_failed_package_week_counts_as_a_gap(self):
        rows = [row(34, "npm_downloads", {"a": {"toplam_30g": 5}}),
                row(35, "npm_downloads", {"a": {"toplam_30g": 6}, "b": {"hata": "429"}}),
                row(36, "npm_downloads", {"a": {"toplam_30g": 7}})]
        s = summary(rows, "npm_downloads")
        assert s["usable_weeks"] == 2 and s["gap_weeks"] == 1 and s["latest_value"] == 7

    def test_one_summary_per_endpoint_sorted_by_name(self):
        rows = [row(34, ozet=x402(1)), row(34, "apify_store", {"magaza_toplam_aktor": 9})]
        assert [s["endpoint"] for s in es.summarise(ws.weekly(rows))] == ["apify_store", "x402_discovery"]

    def test_empty_input(self):
        assert es.summarise([]) == []


class TestMain:
    def run(self, capsys, *args):
        code = es.main(list(args))
        return code, capsys.readouterr()

    def test_text_output(self, tmp_path, capsys):
        p = series(tmp_path, [row(34, ozet=x402(15149)), row(36, ozet=x402(15300)),
                              row(34, "sherlock_contests", {"olculemedi": "x"})])
        code, out = self.run(capsys, "--series", str(p))
        lines = out.out.splitlines()
        assert code == 0
        assert lines[0] == "%-28s  no usable value" % "sherlock_contests"
        assert lines[1].split() == ["x402_discovery", "2026-W34", "..", "2026-W36", "2", "usable", "1", "gap",
                                    "latest", "15,300", "(%s)" % T[36]]

    def test_json_output(self, tmp_path, capsys):
        p = series(tmp_path, [row(34, ozet=x402(1))])
        code, out = self.run(capsys, "--series", str(p), "--json")
        assert code == 0 and [json.loads(x) for x in out.out.splitlines()] == [
            {"endpoint": "x402_discovery", "first_week": "2026-W34", "last_week": "2026-W34",
             "usable_weeks": 1, "gap_weeks": 0, "latest_value": 1, "latest_zaman_utc": T[34]}]

    def test_csv_output_leaves_missing_fields_empty(self, tmp_path, capsys):
        p = series(tmp_path, [row(34, ozet=x402(1)), row(34, "sherlock_contests", {"olculemedi": "x"}),
                              row(34, "defillama_fees_ai_agents", {"ai_total30d": 902574.56})])
        code, out = self.run(capsys, "--series", str(p), "--csv")
        rows = list(csv.reader(io.StringIO(out.out)))
        assert code == 0 and rows[0] == es.COLUMNS
        assert rows[1] == ["defillama_fees_ai_agents", "2026-W34", "2026-W34", "1", "0", "902574.56", T[34]]
        assert rows[2] == ["sherlock_contests", "", "", "0", "0", "", ""]
        assert rows[3] == ["x402_discovery", "2026-W34", "2026-W34", "1", "0", "1", T[34]]

    def test_endpoint_filter(self, tmp_path, capsys):
        p = series(tmp_path, [row(34, ozet=x402(1)), row(34, "apify_store", {"magaza_toplam_aktor": 9})])
        code, out = self.run(capsys, "--series", str(p), "--json", "--endpoint", "apify_store")
        assert [json.loads(x)["endpoint"] for x in out.out.splitlines()] == ["apify_store"]

    def test_csv_and_json_together_are_rejected(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as e:
            es.main(["--series", str(series(tmp_path, [])), "--csv", "--json"])
        assert e.value.code == 2

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        code, out = self.run(capsys, "--series", str(tmp_path / "yok.ndjson"))
        assert code == 1 and "error:" in out.err

    def test_line_that_is_not_json_exits_with_an_error(self, tmp_path, capsys):
        p = tmp_path / "s.ndjson"
        p.write_text("{bozuk\n", encoding="utf-8")
        code, out = self.run(capsys, "--series", str(p))
        assert code == 1 and "line 1" in out.err

    def test_empty_series_prints_nothing(self, tmp_path, capsys):
        code, out = self.run(capsys, "--series", str(series(tmp_path, [])))
        assert code == 0 and out.out == ""

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            es.main(["--help"])
        assert "missing data is never counted as zero" in " ".join(capsys.readouterr().out.split())


def test_real_series_summary_matches_the_weekly_values():
    entries = ws.weekly(ws.read_rows(KOK / "ai-arz-serisi.ndjson"))
    sums = es.summarise(entries)
    assert sums
    for s in sums:
        own = [e for e in entries if e["endpoint"] == s["endpoint"]]
        usable = [e for e in own if e["value"] is not None]
        assert s["usable_weeks"] == len(usable)
        if usable:
            assert s["latest_value"] == usable[-1]["value"]
            assert s["usable_weeks"] + s["gap_weeks"] == sum(
                1 for e in own if s["first_week"] <= e["week"] <= s["last_week"])
