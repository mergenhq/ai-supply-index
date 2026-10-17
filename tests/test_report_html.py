"""Tests for examples/report_html.py — the page is parsed with html.parser; fixtures live under
tmp_path, and the published series is read only up to 2026-10-05T23:59:59."""
import importlib.util
import json
from html.parser import HTMLParser

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("report_html", KOK / "examples" / "report_html.py")
rh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rh)
ws = rh.weekly_series

CUTOFF = "2026-10-05T23:59:59"
T = {34: "2026-08-18T07:00:00+00:00", 35: "2026-08-25T07:00:00+00:00", 36: "2026-09-01T07:00:00+00:00"}


class Page(HTMLParser):
    """Collects tables (id -> rows of cells with attributes), tags seen and external references."""
    def __init__(self):
        super().__init__()
        self.tables, self.tags, self.refs = {}, [], []
        self._table = self._row = self._cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        for key in ("src", "href"):
            if a.get(key):
                self.refs.append(a[key])
        if tag == "table":
            self._table = self.tables.setdefault(a.get("id"), [])
        elif tag == "tr" and self._table is not None:
            self._row = {"class": a.get("class"), "cells": []}
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"tag": tag, "text": "", "attrs": a}

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row["cells"].append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table":
            self._table = None


def parse(html):
    p = Page()
    p.feed(html)
    p.close()
    return p


def row(week, value=None, uc="x402_discovery", durum="OK", ozet=None):
    r = {"zaman_utc": T[week], "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    elif value is not None:
        r["ozet"] = {"kaynak_sayisi": value}
    return r


def run(tmp_path, capsys, rows, *args):
    src = tmp_path / "s.ndjson"
    src.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert rh.main(["--series", str(src), *args]) == 0
    return capsys.readouterr().out


def body(table):
    return [[c["text"] for c in r["cells"]] for r in table if r["cells"][0]["tag"] == "td"]


class TestTables:
    def test_one_table_per_endpoint_with_the_four_columns(self, tmp_path, capsys):
        p = parse(run(tmp_path, capsys, [row(34, 15149), row(34, uc="apify_store", ozet={"magaza_toplam_aktor": 9})]))
        assert sorted(p.tables) == ["endpoint-apify_store", "endpoint-x402_discovery"]
        head = [c["text"] for c in p.tables["endpoint-x402_discovery"][0]["cells"]]
        assert head == ["week", "value", "run", "gap"]

    def test_value_rows(self, tmp_path, capsys):
        p = parse(run(tmp_path, capsys, [row(34, 15149), row(35, 15300)]))
        t = p.tables["endpoint-x402_discovery"]
        assert body(t) == [["2026-W34", "15,149", T[34], ""], ["2026-W35", "15,300", T[35], ""]]
        assert t[1]["cells"][1]["attrs"]["data-value"] == "15149"

    def test_gap_rows_are_empty_never_zero(self, tmp_path, capsys):
        p = parse(run(tmp_path, capsys, [row(34, 1), row(35, durum="HATA"), row(36, 3)]))
        t = p.tables["endpoint-x402_discovery"]
        gap = t[2]
        assert gap["class"] == "gap"
        assert [c["text"] for c in gap["cells"]] == ["2026-W35", "", "", "rows present, none usable"]
        assert "data-value" not in gap["cells"][1]["attrs"]

    def test_week_without_rows_is_a_gap(self, tmp_path, capsys):
        p = parse(run(tmp_path, capsys, [row(34, 1), row(36, 3)]))
        assert body(p.tables["endpoint-x402_discovery"])[1] == ["2026-W35", "", "", "no rows"]

    def test_unusable_rows_follow_the_weekly_series_rules(self, tmp_path, capsys):
        rows = [row(34, 1), row(35, ozet={"kaynak_sayisi": 0, "olculemedi": "schema broken"})]
        assert body(parse(run(tmp_path, capsys, rows)).tables["endpoint-x402_discovery"])[1][1] == ""

    def test_measured_zero_is_written(self, tmp_path, capsys):
        p = parse(run(tmp_path, capsys, [row(34, uc="sherlock_contests", ozet={"acik_yarisma": 0})]))
        assert body(p.tables["endpoint-sherlock_contests"]) == [["2026-W34", "0", T[34], ""]]

    def test_endpoint_filter(self, tmp_path, capsys):
        rows = [row(34, 1), row(34, uc="apify_store", ozet={"magaza_toplam_aktor": 9})]
        assert list(parse(run(tmp_path, capsys, rows, "--endpoint", "apify_store")).tables) == ["endpoint-apify_store"]


class TestPage:
    def test_standalone_without_script_or_external_files(self, tmp_path, capsys):
        p = parse(run(tmp_path, capsys, [row(34, 1)]))
        assert "script" not in p.tags and "link" not in p.tags and "img" not in p.tags
        assert p.refs == []

    def test_text_is_escaped(self, tmp_path, capsys):
        html = rh.page([{"week": "2026-W34", "endpoint": "x402_discovery", "value": None, "gap": "<b>&"}], "a<b.ndjson", "0" * 64)
        assert "<b>&" not in html and "&lt;b&gt;&amp;" in html and "a&lt;b.ndjson" in html

    def test_empty_series(self, tmp_path, capsys):
        p = parse(run(tmp_path, capsys, []))
        assert p.tables == {}

    def test_out_file(self, tmp_path, capsys):
        src = tmp_path / "s.ndjson"
        src.write_text(json.dumps(row(34, 1)) + "\n", encoding="utf-8")
        out = tmp_path / "r.html"
        assert rh.main(["--series", str(src), "--out", str(out)]) == 0 and capsys.readouterr().out == ""
        assert "endpoint-x402_discovery" in parse(out.read_text(encoding="utf-8")).tables

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert rh.main(["--series", str(tmp_path / "yok")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            rh.main(["--help"])
        assert "Gaps are empty, never 0" in " ".join(capsys.readouterr().out.split())


def test_published_rows_up_to_the_cutoff_match_the_weekly_values(tmp_path, capsys):
    rows = [r for r in ws.read_rows(KOK / "ai-arz-serisi.ndjson") if r["zaman_utc"] <= CUTOFF]
    p = parse(run(tmp_path, capsys, rows))
    want = ws.weekly(rows)
    assert want and len(p.tables) == len({e["endpoint"] for e in want})
    for e in want:
        cells = next(r["cells"] for r in p.tables["endpoint-" + e["endpoint"]] if r["cells"][0]["text"] == e["week"])
        if e["value"] is None:
            assert cells[1]["text"] == "" and cells[3]["text"] == e["gap"]
        else:
            assert cells[1]["attrs"]["data-value"] == repr(e["value"]) and cells[2]["text"] == e["zaman_utc"]
