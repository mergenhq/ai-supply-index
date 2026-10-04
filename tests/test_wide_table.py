"""Tests for examples/wide_table.py — synthetic series under tmp_path; the real series is only read."""
import csv
import importlib.util
import io
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("wide_table", KOK / "examples" / "wide_table.py")
wt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wt)
ws = wt.weekly_series

T = {34: "2026-08-18T07:00:00+00:00", 35: "2026-08-25T07:00:00+00:00",
     36: "2026-09-01T07:00:00+00:00", 37: "2026-09-08T07:00:00+00:00"}


def row(week, uc="x402_discovery", ozet=None, durum="OK", stamp=None):
    r = {"zaman_utc": stamp or T[week], "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def x402(n):
    return {"kaynak_sayisi": n}


def apify(n):
    return {"magaza_toplam_aktor": n}


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def table(tmp_path, capsys, rows, *args):
    assert wt.main(["--series", str(series(tmp_path, rows)), *args]) == 0
    return list(csv.reader(io.StringIO(capsys.readouterr().out)))


class TestWide:
    def test_one_row_per_week_one_column_per_endpoint(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, ozet=x402(1)), row(34, "apify_store", apify(10)),
                                       row(35, ozet=x402(2)), row(35, "apify_store", apify(11))])
        assert out == [["week", "apify_store", "x402_discovery"],
                       ["2026-W34", "10", "1"],
                       ["2026-W35", "11", "2"]]

    def test_unusable_week_is_an_empty_cell_not_zero(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, ozet=x402(1)), row(35, durum="HATA"), row(36, ozet=x402(3))])
        assert out[2] == ["2026-W35", ""]

    def test_week_without_rows_is_a_row_with_empty_cells(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, ozet=x402(1)), row(36, ozet=x402(3))])
        assert [r[0] for r in out[1:]] == ["2026-W34", "2026-W35", "2026-W36"] and out[2] == ["2026-W35", ""]

    def test_weeks_before_an_endpoint_first_row_are_empty(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, ozet=x402(1)), row(35, ozet=x402(2)),
                                       row(35, "apify_store", apify(10))])
        assert out[1] == ["2026-W34", "", "1"] and out[2] == ["2026-W35", "10", "2"]

    def test_olculemedi_and_failed_package_are_empty(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [
            row(34, "sherlock_contests", {"acik_yarisma": 0, "olculemedi": "schema broken"}),
            row(34, "npm_downloads", {"a": {"toplam_30g": 5}, "b": {"hata": "429"}}),
            row(34, ozet=x402(1))])
        assert out == [["week", "npm_downloads", "sherlock_contests", "x402_discovery"],
                       ["2026-W34", "", "", "1"]]

    def test_measured_zero_is_written_as_zero(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, "sherlock_contests", {"acik_yarisma": 0})])
        assert out[1] == ["2026-W34", "0"]

    def test_last_usable_row_of_the_week_wins(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, ozet=x402(1)),
                                       row(34, ozet=x402(5), stamp="2026-08-20T07:00:00+00:00"),
                                       row(34, durum="HATA", stamp="2026-08-21T07:00:00+00:00")])
        assert out[1] == ["2026-W34", "5"]

    def test_float_value_round_trips(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, "defillama_fees_ai_agents", {"ai_total30d": 902574.56})])
        assert float(out[1][1]) == 902574.56

    def test_endpoint_filter_selects_columns(self, tmp_path, capsys):
        out = table(tmp_path, capsys, [row(34, ozet=x402(1)), row(34, "apify_store", apify(10))],
                    "--endpoint", "x402_discovery")
        assert out == [["week", "x402_discovery"], ["2026-W34", "1"]]

    def test_empty_series_writes_only_the_header(self, tmp_path, capsys):
        assert table(tmp_path, capsys, []) == [["week"]]

    def test_wide_from_entries(self):
        header, rows = wt.wide(ws.weekly([row(34, ozet=x402(1)), row(36, ozet=x402(3))]))
        assert header == ["week", "x402_discovery"]
        assert rows == [["2026-W34", 1], ["2026-W35", None], ["2026-W36", 3]]


class TestMain:
    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert wt.main(["--series", str(tmp_path / "yok.ndjson")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_line_that_is_not_json_exits_with_an_error(self, tmp_path, capsys):
        p = tmp_path / "s.ndjson"
        p.write_text("42\n", encoding="utf-8")
        assert wt.main(["--series", str(p)]) == 1
        assert "not a JSON object" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            wt.main(["--help"])
        assert "never 0" in " ".join(capsys.readouterr().out.split())


def test_real_series_cells_match_the_weekly_values(capsys):
    entries = ws.weekly(ws.read_rows(KOK / "ai-arz-serisi.ndjson"))
    assert wt.main([]) == 0
    out = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    header = out[0]
    val = {(e["week"], e["endpoint"]): e["value"] for e in entries}
    assert len(out) > 1 and header[0] == "week"
    for r in out[1:]:
        for name, cell in zip(header[1:], r[1:]):
            v = val.get((r[0], name))
            assert (cell == "") == (v is None)
            if v is not None:
                assert float(cell) == v
