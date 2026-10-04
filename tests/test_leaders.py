"""Tests for examples/leaders.py — small fixture files under tmp_path with made-up names;
the published series is only read."""
import csv
import importlib.util
import io
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("leaders", KOK / "examples" / "leaders.py")
ld = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ld)
ws = ld.weekly_series

T = {34: "2026-08-18T07:00:00+00:00", 35: "2026-08-25T07:00:00+00:00",
     36: "2026-09-01T07:00:00+00:00", 37: "2026-09-08T07:00:00+00:00"}


def top5(*names_values):
    return {"ai_total30d": 100.0, "ai_top5_30d": [{"ad": n, "usd30d": v} for n, v in names_values]}


def row(week, ozet=None, uc="defillama_fees_ai_agents", durum="OK", stamp=None):
    r = {"zaman_utc": stamp or T[week], "uc": uc, "durum": durum}
    if ozet is not None:
        r["ozet"] = ozet
    return r


def series(tmp_path, rows):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def by_week(entries):
    out = {}
    for e in entries:
        out.setdefault(e["week"], []).append(e)
    return out


def summary(entries):
    return [(e["rank"], e["name"], e["status"], e["moved"]) for e in entries]


class TestRanks:
    def test_first_week_has_no_comparison(self):
        w = by_week(ld.leaders([row(34, top5(("A", 30), ("B", 20)))], "defillama_fees_ai_agents"))
        assert summary(w["2026-W34"]) == [(1, "A", "no comparison", None), (2, "B", "no comparison", None)]
        assert w["2026-W34"][0]["value"] == 30 and w["2026-W34"][0]["zaman_utc"] == T[34]

    def test_same_up_down_new_left(self):
        rows = [row(34, top5(("A", 30), ("B", 20), ("C", 10))),
                row(35, top5(("B", 40), ("A", 35), ("D", 5)))]
        w = by_week(ld.leaders(rows, "defillama_fees_ai_agents"))
        assert summary(w["2026-W35"]) == [(1, "B", "up", 1), (2, "A", "down", -1), (3, "D", "new", None),
                                          (None, "C", "left", None)]
        left = w["2026-W35"][-1]
        assert left["value"] is None and left["zaman_utc"] == T[35]

    def test_unchanged_list_is_same(self):
        rows = [row(34, top5(("A", 3), ("B", 2))), row(35, top5(("A", 4), ("B", 3)))]
        assert [e["status"] for e in by_week(ld.leaders(rows, "defillama_fees_ai_agents"))["2026-W35"]] == ["same", "same"]

    def test_last_usable_row_of_the_week_gives_the_list(self):
        rows = [row(34, top5(("A", 3))), row(34, top5(("Z", 9)), stamp="2026-08-20T07:00:00+00:00"),
                row(34, durum="HATA", stamp="2026-08-21T07:00:00+00:00")]
        assert [e["name"] for e in ld.leaders(rows, "defillama_fees_ai_agents")] == ["Z"]

    @pytest.mark.parametrize("endpoint, ozet, want", [
        ("x402_discovery", {"kaynak_sayisi": 5, "top10_cagri": [{"cagri": 9, "kaynak": "https://r"}]}, ("https://r", 9)),
        ("sherlock_leaderboard", {"arastirmaci_sayisi": 5, "top10": [{"handle": "h1", "odeme": 7.5}]}, ("h1", 7.5)),
        ("apify_store", {"magaza_toplam_aktor": 5, "top10": [{"aktor": "u/a", "kullanici": 3}]}, ("u/a", 3)),
        ("hf_models", {"indirme_dagilimi": {"toplam": 1.0}, "top10": [{"id": "o/m", "indirme": 8, "begeni": 1}]}, ("o/m", 8)),
    ])
    def test_every_endpoint_list_is_read(self, endpoint, ozet, want):
        e = ld.leaders([row(34, ozet, uc=endpoint)], endpoint)
        assert [(x["name"], x["value"]) for x in e] == [want]


class TestGaps:
    def test_gap_week_is_a_gap_and_the_next_week_is_not_compared(self):
        rows = [row(34, top5(("A", 3))), row(35, durum="HTTP-HATA"), row(36, top5(("B", 4)))]
        w = by_week(ld.leaders(rows, "defillama_fees_ai_agents"))
        assert len(w["2026-W35"]) == 1 and w["2026-W35"][0]["gap"] == "rows present, none usable"
        assert w["2026-W35"][0]["rank"] is None and w["2026-W35"][0]["name"] is None
        assert summary(w["2026-W36"]) == [(1, "B", "no comparison", None)]

    def test_week_without_rows_is_a_gap(self):
        w = by_week(ld.leaders([row(34, top5(("A", 3))), row(36, top5(("A", 4)))], "defillama_fees_ai_agents"))
        assert w["2026-W35"][0]["gap"] == "no rows"

    def test_list_missing_from_the_chosen_row_is_a_gap(self):
        rows = [row(34, top5(("A", 3))), row(35, {"ai_total30d": 5.0}), row(36, top5(("A", 4)))]
        w = by_week(ld.leaders(rows, "defillama_fees_ai_agents"))
        assert w["2026-W35"][0]["gap"] == "list not in this row" and w["2026-W35"][0]["zaman_utc"] == T[35]
        assert w["2026-W36"][0]["status"] == "no comparison"

    def test_empty_list_is_a_list_not_a_gap(self):
        rows = [row(34, top5(("A", 3))), row(35, top5())]
        w = by_week(ld.leaders(rows, "defillama_fees_ai_agents"))
        assert summary(w["2026-W35"]) == [(None, "A", "left", None)]

    def test_non_numeric_value_is_empty(self):
        e = ld.leaders([row(34, top5(("A", None), ("B", "x")))], "defillama_fees_ai_agents")
        assert [x["value"] for x in e] == [None, None]


class TestChangesOnly:
    def test_only_moves_are_listed(self):
        rows = [row(34, top5(("A", 3), ("B", 2), ("C", 1))), row(35, top5(("A", 4), ("C", 3), ("D", 1))),
                row(36, durum="HATA")]
        e = ld.leaders(rows, "defillama_fees_ai_agents", changes_only=True)
        assert [(x["week"], x["name"], x["status"]) for x in e] == [
            ("2026-W35", "C", "up"), ("2026-W35", "D", "new"), ("2026-W35", "B", "left")]


class TestMain:
    def out(self, capsys, tmp_path, rows, *args):
        assert ld.main(["--series", str(series(tmp_path, rows)), "--endpoint", "defillama_fees_ai_agents", *args]) == 0
        return capsys.readouterr().out

    def test_text(self, tmp_path, capsys):
        lines = self.out(capsys, tmp_path, [row(34, top5(("A", 30000), ("B", 20))), row(35, top5(("B", 40))),
                                            row(37, top5(("B", 1)))]).splitlines()
        assert lines[0].startswith("defillama_fees_ai_agents: rank, name, 30-day fees (USD)")
        assert lines[1].split() == ["2026-W34", "1", "A", "30,000", "no", "comparison"]
        assert lines[3].split() == ["2026-W35", "1", "B", "40", "up", "+1"]
        assert lines[4].split() == ["2026-W35", "-", "A", "left"]
        assert lines[5] == "2026-W36  GAP (no rows)"

    def test_csv_leaves_missing_values_empty(self, tmp_path, capsys):
        got = list(csv.reader(io.StringIO(self.out(capsys, tmp_path,
                                                   [row(34, top5(("A", 3))), row(36, top5(("A", 4)))], "--csv"))))
        assert got[0] == ld.COLUMNS
        assert got[1] == ["2026-W34", "defillama_fees_ai_agents", "1", "A", "3", "no comparison", "", T[34], ""]
        assert got[2] == ["2026-W35", "defillama_fees_ai_agents", "", "", "", "", "", "", "no rows"]

    def test_json(self, tmp_path, capsys):
        lines = self.out(capsys, tmp_path, [row(34, top5(("A", 3)))], "--json").splitlines()
        assert json.loads(lines[0])["status"] == "no comparison"

    def test_endpoint_must_have_a_list(self, capsys):
        with pytest.raises(SystemExit):
            ld.main(["--endpoint", "npm_downloads"])

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        assert ld.main(["--series", str(tmp_path / "yok"), "--endpoint", "hf_models"]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            ld.main(["--help"])
        assert "same, up, down, new or left" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("endpoint", sorted(ld.LISTS))
def test_published_series_lists_match_the_chosen_rows(endpoint):
    rows = ws.read_rows(KOK / "ai-arz-serisi.ndjson")
    by_key = {(r["zaman_utc"], r["uc"]): r for r in rows}
    key, name_key, value_key, _ = ld.LISTS[endpoint]
    got = by_week(ld.leaders(rows, endpoint))
    assert got
    for week, entries in got.items():
        listed = [e for e in entries if e.get("rank") is not None]
        if not listed:
            continue
        src = by_key[(listed[0]["zaman_utc"], endpoint)]["ozet"][key]
        assert [(e["name"], e["value"]) for e in listed] == [(str(x[name_key]), x[value_key]) for x in src]
