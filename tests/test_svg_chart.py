"""Tests for examples/svg_chart.py — the SVG is parsed with xml.etree; fixtures live under tmp_path."""
import importlib.util
import json
import xml.etree.ElementTree as ET

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("svg_chart", KOK / "examples" / "svg_chart.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)
ws = sc.weekly_series

NS = {"s": "http://www.w3.org/2000/svg"}
T = {34: "2026-08-18", 35: "2026-08-25", 36: "2026-09-01", 37: "2026-09-08", 38: "2026-09-15"}


def row(week, value=None, durum="OK", uc="x402_discovery", ozet=None):
    r = {"zaman_utc": T[week] + "T07:00:00+00:00", "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    elif value is not None:
        r["ozet"] = {"kaynak_sayisi": value}
    return r


def svg_for(rows, endpoint="x402_discovery"):
    return ET.fromstring(sc.render(endpoint, ws.weekly(rows, [endpoint])))


def circles(root):
    return root.findall(".//s:g[@class='series']/s:circle", NS)


def polylines(root):
    return root.findall(".//s:g[@class='series']/s:polyline", NS)


def texts(root, cls):
    return ["".join(t.itertext()) for t in root.iter("{%s}text" % NS["s"]) if t.get("class") == cls]


class TestPoints:
    def test_one_circle_per_week_with_a_value(self):
        root = svg_for([row(34, 10), row(35, 12), row(36, 11)])
        assert [(c.get("data-week"), c.get("data-value")) for c in circles(root)] == [
            ("2026-W34", "10"), ("2026-W35", "12"), ("2026-W36", "11")]

    def test_unbroken_weeks_are_one_polyline(self):
        root = svg_for([row(34, 10), row(35, 12), row(36, 11)])
        assert len(polylines(root)) == 1 and len(polylines(root)[0].get("points").split()) == 3

    def test_points_go_left_to_right_and_higher_values_higher(self):
        root = svg_for([row(34, 10), row(35, 20)])
        a, b = circles(root)
        assert float(a.get("cx")) < float(b.get("cx")) and float(a.get("cy")) > float(b.get("cy"))

    def test_polyline_runs_through_the_circles(self):
        root = svg_for([row(34, 10), row(35, 12)])
        pts = [tuple(map(float, p.split(","))) for p in polylines(root)[0].get("points").split()]
        assert pts == [(float(c.get("cx")), float(c.get("cy"))) for c in circles(root)]


class TestGaps:
    def test_gap_week_breaks_the_line(self):
        root = svg_for([row(34, 10), row(35, 12), row(36, durum="HATA"), row(37, 13), row(38, 14)])
        lines = polylines(root)
        assert len(lines) == 2 and [len(p.get("points").split()) for p in lines] == [2, 2]

    def test_gap_week_has_no_point_and_no_line_across_it(self):
        root = svg_for([row(34, 10), row(36, 12)])          # W35 has no rows
        assert [c.get("data-week") for c in circles(root)] == ["2026-W34", "2026-W36"]
        assert polylines(root) == []

    def test_gap_weeks_are_marked_with_their_reason(self):
        root = svg_for([row(34, 10), row(35, durum="HTTP-HATA"), row(36, 12)])
        gap = root.find(".//s:g[@class='gaps']/s:text", NS)
        assert gap.get("data-week") == "2026-W35"
        assert "rows present, none usable" in "".join(gap.itertext())

    def test_unusable_rows_follow_the_weekly_series_rules(self):
        rows = [row(34, 10), row(35, ozet={"kaynak_sayisi": 0, "olculemedi": "schema broken"}), row(36, 12)]
        assert [c.get("data-week") for c in circles(svg_for(rows))] == ["2026-W34", "2026-W36"]

    def test_isolated_point_has_a_circle_but_no_line(self):
        root = svg_for([row(34, 10), row(35, durum="HATA"), row(36, 12), row(37, durum="HATA"), row(38, 9)])
        assert len(circles(root)) == 3 and polylines(root) == []

    def test_measured_zero_is_drawn(self):
        rows = [row(34, uc="sherlock_contests", ozet={"acik_yarisma": 0}),
                row(35, uc="sherlock_contests", ozet={"acik_yarisma": 1})]
        root = svg_for(rows, "sherlock_contests")
        assert [c.get("data-value") for c in circles(root)] == ["0", "1"]


class TestAxes:
    def test_title_and_axis_labels(self):
        root = svg_for([row(34, 10), row(35, 12)])
        assert texts(root, "chart-title") == ["x402_discovery: resources registered per ISO week"]
        assert texts(root, "axis-label") == ["resources registered", "ISO week"]

    def test_y_ticks_cover_the_values(self):
        root = svg_for([row(34, 15017), row(35, 17820)])
        ticks = [float(t.replace(",", "")) for t in
                 ["".join(x.itertext()) for x in root.findall(".//s:g[@class='y-axis']/s:text", NS)
                  if x.get("class") == "tick"]]
        assert ticks == sorted(ticks) and ticks[0] <= 15017 and ticks[-1] >= 17820

    def test_x_tick_labels_are_weeks(self):
        root = svg_for([row(34, 10), row(35, 12), row(36, 11)])
        labels = ["".join(x.itertext()) for x in root.findall(".//s:g[@class='x-axis']/s:text", NS)
                  if x.get("class") == "tick"]
        assert labels == ["2026-W34", "2026-W35", "2026-W36"]

    @pytest.mark.parametrize("lo, hi", [(0, 0), (5, 5), (0.2, 0.3), (751776, 1137008), (0, 3)])
    def test_nice_ticks_are_increasing_and_cover_the_range(self, lo, hi):
        t = sc.nice_ticks(lo, hi)
        assert t == sorted(t) and len(set(t)) == len(t) and t[0] <= lo and t[-1] >= hi

    def test_non_negative_data_has_no_negative_tick(self):
        assert min(sc.nice_ticks(0, 0)) == 0 and min(sc.nice_ticks(0, 3)) == 0

    def test_endpoint_without_usable_values(self):
        root = svg_for([row(34, durum="HATA")])
        assert circles(root) == [] and texts(root, "no-data") == ["no usable value in the series"]


class TestMain:
    def series(self, tmp_path, rows):
        p = tmp_path / "s.ndjson"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return p

    def test_writes_to_standard_output(self, tmp_path, capsys):
        p = self.series(tmp_path, [row(34, 10)])
        assert sc.main(["--series", str(p), "--endpoint", "x402_discovery"]) == 0
        assert ET.fromstring(capsys.readouterr().out).tag == "{%s}svg" % NS["s"]

    def test_writes_to_out_file(self, tmp_path, capsys):
        p, out = self.series(tmp_path, [row(34, 10)]), tmp_path / "c.svg"
        assert sc.main(["--series", str(p), "--endpoint", "x402_discovery", "--out", str(out)]) == 0
        assert capsys.readouterr().out == "" and len(circles(ET.parse(out).getroot())) == 1

    def test_endpoint_is_required(self, capsys):
        with pytest.raises(SystemExit) as e:
            sc.main([])
        assert e.value.code == 2

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert sc.main(["--series", str(tmp_path / "yok"), "--endpoint", "x402_discovery"]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            sc.main(["--help"])
        assert "never drawn as 0" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("endpoint", sorted(ws.VALUES))
def test_published_series_chart_matches_the_weekly_values(endpoint):
    entries = ws.weekly(ws.read_rows(KOK / "ai-arz-serisi.ndjson"), [endpoint])
    root = ET.fromstring(sc.render(endpoint, entries))
    want = [(e["week"], repr(e["value"])) for e in entries if e["value"] is not None]
    assert [(c.get("data-week"), c.get("data-value")) for c in circles(root)] == want
