"""Tests for examples/histogram.py — small fixture files under tmp_path; the published series is only read."""
import csv
import importlib.util
import io
import json

import pytest

import collector
from conftest import KOK

_spec = importlib.util.spec_from_file_location("histogram", KOK / "examples" / "histogram.py")
hg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hg)
ws = hg.weekly_series

T = {34: "2026-08-18T07:00:00+00:00", 35: "2026-08-25T07:00:00+00:00", 36: "2026-09-01T07:00:00+00:00"}


def dist(values, buckets=(1, 10, 100)):
    return collector.dagilim_ozeti(values, list(buckets))


def row(week, ozet=None, uc="x402_discovery", durum="OK", stamp=None):
    r = {"zaman_utc": stamp or T[week], "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def x402(cagri=None, **extra):
    o = {"kaynak_sayisi": 10, **extra}
    if cagri is not None:
        o["cagri_30g"] = cagri
    return o


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def weeks(rows, field="cagri_30g"):
    return {w["week"]: w for w in hg.histogram(rows, "x402_discovery", field)}


class TestBuckets:
    def test_counts_and_shares_in_stored_order(self):
        w = weeks([row(34, x402(dist([0.5, 2, 3, 50])))])["2026-W34"]
        assert w["n"] == 4 and w["zaman_utc"] == T[34] and "gap" not in w
        assert w["buckets"] == [("<1", 1, 0.25), ("1-10", 2, 0.5), ("10-100", 1, 0.25), (">=100", 0, 0.0)]

    def test_shares_add_up_to_one(self):
        w = weeks([row(34, x402(dist([0, 1, 5, 9, 12, 400, 7000])))])["2026-W34"]
        assert sum(s for _, _, s in w["buckets"]) == pytest.approx(1.0)

    def test_last_usable_row_of_the_week_wins(self):
        rows = [row(34, x402(dist([1]))), row(34, x402(dist([1, 2, 3])), stamp="2026-08-20T07:00:00+00:00"),
                row(34, durum="HATA", stamp="2026-08-21T07:00:00+00:00")]
        assert weeks(rows)["2026-W34"]["n"] == 3

    def test_histogram_fields(self):
        rows = [row(34, x402(dist([1]), odeyen_30g={"n": 0}, top10_cagri=[])),
                row(35, {"kaynak_sayisi": 1, "odeyen_30g": dist([2])})]
        assert hg.histogram_fields(rows, "x402_discovery") == ["cagri_30g", "odeyen_30g"]


class TestGaps:
    def test_week_without_rows_is_a_gap(self):
        w = weeks([row(34, x402(dist([1]))), row(36, x402(dist([2])))])["2026-W35"]
        assert w["gap"] == "no rows" and w["buckets"] == [] and w["n"] is None

    def test_unusable_week_is_a_gap(self):
        rows = [row(34, x402(dist([1]))), row(35, x402(dist([5]), olculemedi="page cap reached"))]
        assert weeks(rows)["2026-W35"]["gap"] == "rows present, none usable"

    def test_field_not_in_the_chosen_row_is_a_gap(self):
        w = weeks([row(34, x402(dist([1]))), row(35, x402())])["2026-W35"]
        assert w["gap"] == "field not in this row" and w["zaman_utc"] == T[35]

    def test_empty_distribution_has_no_buckets_and_no_gap(self):
        w = weeks([row(34, x402(dist([1]))), row(35, x402({"n": 0}))])["2026-W35"]
        assert w["n"] == 0 and w["buckets"] == [] and "gap" not in w

    def test_distribution_without_histogram_is_a_gap(self):
        w = weeks([row(34, x402(dist([1]))), row(35, x402({"n": 3, "p50": 1}))])["2026-W35"]
        assert w["gap"] == "no histogram in this field"


class TestMain:
    def out(self, capsys, tmp_path, rows, *args):
        assert hg.main(["--series", str(series(tmp_path, rows)), "--endpoint", "x402_discovery", *args]) == 0
        return capsys.readouterr().out

    def test_text(self, tmp_path, capsys):
        lines = self.out(capsys, tmp_path, [row(34, x402(dist([0.5, 2, 3, 50]))), row(36, x402(dist([1])))]).splitlines()
        assert lines[0] == "x402_discovery cagri_30g: bucket counts and share of n per ISO week"
        assert lines[1].split() == ["2026-W34", "n=4", "(%s)" % T[34]]
        assert lines[3].split() == ["1-10", "2", "50.0%", "#" * 20]
        assert "2026-W35  GAP (no rows)" in lines

    def test_csv_one_row_per_bucket_and_empty_gaps(self, tmp_path, capsys):
        got = list(csv.reader(io.StringIO(self.out(capsys, tmp_path, [row(34, x402(dist([2]))), row(36, x402({"n": 0}))], "--csv"))))
        assert got[0] == hg.COLUMNS
        assert got[2] == ["2026-W34", "x402_discovery", "cagri_30g", "1-10", "1", "1.0", "1", T[34], ""]
        assert ["2026-W35", "x402_discovery", "cagri_30g", "", "", "", "", "", "no rows"] in got
        assert got[-1] == ["2026-W36", "x402_discovery", "cagri_30g", "", "", "", "0", T[36], ""]

    def test_json(self, tmp_path, capsys):
        (line,) = self.out(capsys, tmp_path, [row(34, x402(dist([2])))], "--json").splitlines()
        assert json.loads(line)["buckets"][1] == {"bucket": "1-10", "count": 1, "share": 1.0}

    def test_field_option(self, tmp_path, capsys):
        rows = [row(34, x402(dist([2]), odeyen_30g=dist([200])))]
        assert ">=100" in self.out(capsys, tmp_path, rows, "--field", "odeyen_30g", "--csv").splitlines()[4]

    def test_unknown_field_and_endpoint_without_histograms(self, tmp_path, capsys):
        p = series(tmp_path, [row(34, x402(dist([2]))), row(34, {"a": {"toplam_30g": 1}}, uc="npm_downloads")])
        assert hg.main(["--series", str(p), "--endpoint", "x402_discovery", "--field", "yok"]) == 1
        assert hg.main(["--series", str(p), "--endpoint", "npm_downloads"]) == 1
        assert capsys.readouterr().err.count("error:") == 2

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert hg.main(["--series", str(tmp_path / "yok"), "--endpoint", "x402_discovery"]) == 1

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            hg.main(["--help"])
        assert "never as 0" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("endpoint", ["x402_discovery", "sherlock_leaderboard", "apify_store", "hf_models",
                                      "defillama_fees_ai_agents", "defillama_summary_virtuals"])
def test_published_series_bucket_counts_add_up_to_n(endpoint):
    rows = ws.read_rows(KOK / "ai-arz-serisi.ndjson")
    fields = hg.histogram_fields(rows, endpoint)
    assert fields
    for field in fields:
        for w in hg.histogram(rows, endpoint, field):
            if w["buckets"]:
                assert sum(c for _, c, _ in w["buckets"]) == w["n"]
