"""Tests for examples/weekly_series.py — synthetic series under tmp_path; the real series is only read."""
import importlib.util
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("weekly_series", KOK / "examples" / "weekly_series.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

# ISO weeks: 2026-08-17..23 is W34, 2026-08-24..30 is W35, 2026-08-31..09-06 is W36
W34, W35, W36 = "2026-W34", "2026-W35", "2026-W36"


def row(stamp, uc="x402_discovery", ozet=None, durum="OK"):
    r = {"zaman_utc": stamp, "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def x402(n):
    return {"kaynak_sayisi": n}


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def by_week(entries, uc="x402_discovery"):
    return {e["week"]: e for e in entries if e["endpoint"] == uc}


# ── the README rules ────────────────────────────────────────────────────────
class TestUsable:
    def test_ok_row_with_a_summary_is_usable(self):
        assert ws.usable(row("2026-08-18T07:00:00+00:00", ozet=x402(1)))

    @pytest.mark.parametrize("durum", ["HATA", "HTTP-HATA", "HATA-ICERIDE", None])
    def test_row_with_any_other_status_is_not_usable(self, durum):
        assert not ws.usable(row("2026-08-18T07:00:00+00:00", ozet=x402(1), durum=durum))

    def test_summary_carrying_olculemedi_is_not_usable(self):
        assert not ws.usable(row("t", "sherlock_contests", {"acik_yarisma": None, "olculemedi": "x"}))

    @pytest.mark.parametrize("sub", [{"hata": "429"}, {"toplam_30g": 5, "olculemedi": "1 of 30 day records"}])
    def test_package_sub_summary_carrying_hata_or_olculemedi_makes_the_row_unusable(self, sub):
        assert not ws.usable(row("t", "npm_downloads", {"a": {"toplam_30g": 5}, "b": sub}))

    def test_row_without_an_object_summary_is_not_usable(self):
        assert not ws.usable(row("t")) and not ws.usable(row("t", ozet=[1]))


class TestMissingStaysMissing:
    def test_zero_beside_olculemedi_is_reported_as_a_gap(self, tmp_path):
        rows = [row("2026-08-18T07:00:00+00:00", "sherlock_contests",
                    {"yarisma_sayisi": 301, "acik_yarisma": 0, "olculemedi": "schema broken"})]
        e = by_week(ws.weekly(ws.read_rows(series(tmp_path, rows))), "sherlock_contests")[W34]
        assert e["value"] is None and e["gap"] == "rows present, none usable"

    def test_row_with_a_failed_package_is_reported_as_missing(self, tmp_path):
        rows = [row("2026-08-18T07:00:00+00:00", "pypi_downloads",
                    {"anthropic": {"aynasiz_toplam": 900}, "openai": {"hata": "HTTPError 429"}})]
        e = by_week(ws.weekly(ws.read_rows(series(tmp_path, rows))), "pypi_downloads")[W34]
        assert e["value"] is None

    def test_row_without_a_readable_value_is_reported_as_missing(self, tmp_path):
        rows = [row("2026-08-18T07:00:00+00:00", ozet={"resource_count": 5})]
        assert by_week(ws.weekly(ws.read_rows(series(tmp_path, rows))))[W34]["value"] is None

    def test_measured_zero_is_reported_as_zero(self, tmp_path):
        rows = [row("2026-08-18T07:00:00+00:00", "sherlock_contests", {"acik_yarisma": 0})]
        e = by_week(ws.weekly(ws.read_rows(series(tmp_path, rows))), "sherlock_contests")[W34]
        assert e["value"] == 0 and "gap" not in e


class TestLastUsableRowWins:
    def test_latest_usable_row_of_the_week_wins(self, tmp_path):
        rows = [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                row("2026-08-20T07:00:00+00:00", ozet=x402(2)),
                row("2026-08-19T07:00:00+00:00", ozet=x402(3))]       # file order does not matter
        e = by_week(ws.weekly(rows))[W34]
        assert e["value"] == 2 and e["zaman_utc"] == "2026-08-20T07:00:00+00:00"

    def test_earlier_usable_row_wins_over_later_unusable_rows(self, tmp_path):
        rows = [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                row("2026-08-20T06:30:00+00:00", ozet=x402(2)),
                row("2026-08-20T07:00:00+00:00", durum="HATA"),
                row("2026-08-21T07:00:00+00:00", ozet={"kaynak_sayisi": 9, "olculemedi": "x"})]
        assert by_week(ws.weekly(rows))[W34]["value"] == 2

    def test_weeks_start_on_iso_monday(self):
        rows = [row("2026-08-23T23:59:59+00:00", ozet=x402(1)),     # Sunday, W34
                row("2026-08-24T00:00:00+00:00", ozet=x402(2))]     # Monday, W35
        w = by_week(ws.weekly(rows))
        assert w[W34]["value"] == 1 and w[W35]["value"] == 2

    def test_each_endpoint_gets_its_own_row_per_week(self):
        rows = [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                row("2026-08-19T07:00:00+00:00", "apify_store", {"magaza_toplam_aktor": 7})]
        e = ws.weekly(rows)
        assert [(x["week"], x["endpoint"], x["value"]) for x in e] == [
            (W34, "apify_store", 7), (W34, "x402_discovery", 1)]


class TestGaps:
    def test_week_without_any_row_is_reported_as_a_gap(self):
        rows = [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                row("2026-09-01T07:00:00+00:00", ozet=x402(3))]
        w = by_week(ws.weekly(rows))
        assert list(w) == [W34, W35, W36]
        assert w[W35] == {"week": W35, "endpoint": "x402_discovery", "value": None, "gap": "no rows"}

    def test_week_with_only_unusable_rows_is_reported_as_a_gap(self):
        rows = [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                row("2026-08-25T07:00:00+00:00", durum="HTTP-HATA"),
                row("2026-09-01T07:00:00+00:00", ozet=x402(3))]
        assert by_week(ws.weekly(rows))[W35]["gap"] == "rows present, none usable"

    def test_gaps_run_to_the_last_week_of_the_series(self):
        rows = [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                row("2026-09-01T07:00:00+00:00", "apify_store", {"magaza_toplam_aktor": 7})]
        w = by_week(ws.weekly(rows))
        assert w[W35]["gap"] == "no rows" and w[W36]["gap"] == "no rows"

    def test_endpoint_rows_start_at_its_first_week(self):
        rows = [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                row("2026-09-01T07:00:00+00:00", "apify_store", {"magaza_toplam_aktor": 7})]
        assert list(by_week(ws.weekly(rows), "apify_store")) == [W36]

    def test_weeks_continue_across_the_year_boundary(self):
        rows = [row("2026-12-28T07:00:00+00:00", ozet=x402(1)),     # 2026-W53
                row("2027-01-11T07:00:00+00:00", ozet=x402(2))]     # 2027-W02
        assert list(by_week(ws.weekly(rows))) == ["2026-W53", "2027-W01", "2027-W02"]


# ── input and CLI ───────────────────────────────────────────────────────────
class TestReadRows:
    def test_blank_lines_are_skipped(self, tmp_path):
        p = tmp_path / "s.ndjson"
        p.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
        assert ws.read_rows(p) == [{"a": 1}, {"b": 2}]

    @pytest.mark.parametrize("bad, msg", [("{bozuk", "line 2 is not valid JSON"), ("42", "line 2 is not a JSON object")])
    def test_line_that_is_not_a_json_object_stops_the_run(self, tmp_path, bad, msg):
        p = tmp_path / "s.ndjson"
        p.write_text('{"a": 1}\n%s\n' % bad, encoding="utf-8")
        with pytest.raises(ValueError, match=msg):
            ws.read_rows(p)


class TestMain:
    def test_table_shows_values_and_gaps_by_week(self, tmp_path, capsys):
        p = series(tmp_path, [row("2026-08-18T07:00:00+00:00", ozet=x402(15149)),
                              row("2026-09-01T07:00:00+00:00", ozet=x402(15200))])
        assert ws.main(["--series", str(p)]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[0].startswith("2026-W34  x402_discovery") and "15,149" in out[0]
        assert out[1].startswith("2026-W35  x402_discovery") and "GAP (no rows)" in out[1]
        assert out[1].split() == ["2026-W35", "x402_discovery", "GAP", "(no", "rows)"]

    def test_json_output_lists_only_the_selected_endpoint(self, tmp_path, capsys):
        p = series(tmp_path, [row("2026-08-18T07:00:00+00:00", ozet=x402(1)),
                              row("2026-08-18T07:00:00+00:00", "apify_store", {"magaza_toplam_aktor": 7})])
        assert ws.main(["--series", str(p), "--endpoint", "apify_store", "--json"]) == 0
        lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
        assert lines == [{"week": W34, "endpoint": "apify_store", "value": 7,
                          "zaman_utc": "2026-08-18T07:00:00+00:00"}]

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert ws.main(["--series", str(tmp_path / "yok.ndjson")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            ws.main(["--help"])
        assert "Missing data is printed as GAP, never as zero" in " ".join(capsys.readouterr().out.split())


def test_example_picks_the_same_rows_as_the_readme_snippet():
    """The example and the README snippet pick the same row per week and endpoint."""
    readme = (KOK / "README.md").read_text(encoding="utf-8")
    bolum = readme[readme.index("## Using the series"):]
    kod = bolum[bolum.index("```python") + len("```python"):]
    kod = kod[:kod.index("```")].replace('open("ai-arz-serisi.ndjson"',
                                         'open(%r' % str(KOK / "ai-arz-serisi.ndjson"))
    ns = {}
    exec(compile(kod, "README", "exec"), ns)
    snippet = {(r["week"], r["uc"]): r["zaman_utc"] for r in ns["weekly"] if r["uc"] in ws.VALUES}
    ours = {(e["week"], e["endpoint"]): e["zaman_utc"]
            for e in ws.weekly(ws.read_rows(KOK / "ai-arz-serisi.ndjson")) if e["value"] is not None}
    assert ours == snippet
