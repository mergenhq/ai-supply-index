"""Further checks on collector.py: bucket edges, rounding, page limits, waits between requests
and open-entry classification. Every HTTP call is answered by a fake; time is frozen."""
import json
import urllib.error
from datetime import datetime, timezone

import pytest

import collector as c
from conftest import SIMDI, sabit_datetime

SIMDI_EP = int(SIMDI.timestamp())
GUN = 86400


@pytest.fixture(autouse=True)
def sabit_zaman(monkeypatch):
    bekleme = []
    monkeypatch.setattr(c.time, "time", lambda: float(SIMDI_EP))
    monkeypatch.setattr(c.time, "sleep", bekleme.append)
    monkeypatch.setattr(c, "datetime", sabit_datetime(SIMDI))
    return bekleme


@pytest.fixture
def ag(monkeypatch):
    cagrilar = []

    def kur(yanit):
        def cek(url, ham=False):
            cagrilar.append(url)
            y = yanit(url) if callable(yanit) else yanit
            if isinstance(y, Exception):
                raise y
            return 200, y
        monkeypatch.setattr(c, "cek", cek)
        return cagrilar
    return kur


def iso(ep):
    return datetime.fromtimestamp(ep, timezone.utc).isoformat().replace("+00:00", "Z")


def sayfa_no(url, ad="page"):
    import re
    return int(re.search(r"[?&]%s=(\d+)" % ad, url).group(1))


# ── request settings ────────────────────────────────────────────────────────
def test_requests_use_a_30_second_timeout(monkeypatch):
    gorulen = {}

    class Yanit:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        gorulen["timeout"] = timeout
        return Yanit()
    monkeypatch.setattr(c.urllib.request, "urlopen", urlopen)
    c.cek("https://ornek.test")
    assert gorulen["timeout"] == 30


@pytest.mark.parametrize("fn,yanit,bekleme", [
    (c.uc_x402, lambda u: {"items": [{"quality": {}}] if sayfa_no(u, "offset") == 0 else []}, [0.25]),
    (c.uc_apify_store, lambda u: {"data": {"items": [{}] if sayfa_no(u, "offset") == 0 else []}}, [0.25]),
    (c.uc_sherlock_contests, lambda u: {"items": [], "has_next": sayfa_no(u) == 1}, [0.2]),
    (c.uc_code4rena_audits, lambda u: {"data": {"audits": []},
                                       "pagination": {"nextPage": 2 if sayfa_no(u) == 1 else None}}, [0.2]),
])
def test_wait_between_pages(ag, sabit_zaman, fn, yanit, bekleme):
    ag(yanit)
    fn()
    assert sabit_zaman == bekleme


@pytest.mark.parametrize("fn,liste,bekleme", [
    (c.uc_npm, "NPM_PAKETLER", 0.5), (c.uc_pypi, "PYPI_PAKETLER", 2), (c.uc_github, "GH_DEPOLAR", 1)])
def test_wait_after_each_package(ag, sabit_zaman, monkeypatch, fn, liste, bekleme):
    monkeypatch.setattr(c, liste, ["a/b", "c/d"])
    ag({})
    fn()
    assert sabit_zaman == [bekleme, bekleme]


@pytest.mark.parametrize("fn,liste", [(c.uc_npm, "NPM_PAKETLER"), (c.uc_pypi, "PYPI_PAKETLER"),
                                      (c.uc_github, "GH_DEPOLAR")])
def test_package_error_text_is_cut_to_120_characters(ag, monkeypatch, fn, liste):
    monkeypatch.setattr(c, liste, ["a"])
    ag(RuntimeError("x" * 300))
    assert len(fn()["a"]["hata"]) == 120


# ── distribution summary ────────────────────────────────────────────────────
def test_distribution_rounding_and_percentile_keys():
    o = c.dagilim_ozeti([1.23456, 2.34567, 3.45678], [10])
    assert o["toplam"] == 7.04 and o["maks"] == 3.46
    assert [k for k in o if k.startswith("p")] == ["p10", "p25", "p50", "p75", "p90", "p95", "p99"]
    assert o["p50"] == 2.3457 and o["p10"] == 1.2346
    assert o["top1_pay"] == round(3.45678 / 7.04, 4) and o["top10_pay"] == round(7.03701 / 7.04, 4)


def test_percentiles_pick_the_documented_ranks():
    d = list(range(1, 101))
    o = c.dagilim_ozeti(d, [1000])
    assert [o["p%d" % p] for p in (10, 25, 50, 75, 90, 95, 99)] == [10, 25, 50, 75, 90, 95, 99]


def test_concentration_is_reported_for_a_small_positive_total():
    o = c.dagilim_ozeti([0.5], [1])
    assert o["top1_pay"] == 1.0 and o["top10_pay"] == 1.0


def test_x402_bucket_edges(ag):
    ag({"pagination": {"total": 1}, "items": [{"quality": {"l30DaysTotalCalls": 5, "l30DaysUniquePayers": 3}}]})
    o = c.uc_x402()
    assert list(o["cagri_30g"]["histogram"]) == ["<1", "1-10", "10-100", "100-1000", "1000-10000", ">=10000"]
    assert list(o["odeyen_30g"]["histogram"]) == ["<1", "1-2", "2-5", "5-10", "10-100", ">=100"]


def test_other_bucket_edges(ag, monkeypatch):
    ag({"a": {"payout": 5}})
    assert list(c.uc_sherlock_leaderboard()["omur_boyu_odeme"]["histogram"]) == \
        ["<1", "1-100", "100-1000", "1000-10000", "10000-100000", ">=100000"]
    ag({"protocols": [{"name": "v", "category": "AI Agents", "total30d": 5}]})
    assert list(c.uc_defillama_kategori()["ai_30g_dagilim"]["histogram"]) == \
        ["<100", "100-1000", "1000-10000", "10000-100000", ">=100000"]
    ag({"name": "V", "totalDataChart": [[SIMDI_EP, 5]]})
    assert list(c.uc_defillama_protokol()["son30g_dagilim"]["histogram"]) == \
        ["<1000", "1000-10000", "10000-100000", ">=100000"]
    ag(lambda u: {"data": {"total": 1, "items": [{"stats": {"totalUsers": 5}}] if sayfa_no(u, "offset") == 0
                           else []}})
    assert list(c.uc_apify_store()["toplam_kullanici_dagilimi"]["histogram"]) == \
        ["<1", "1-10", "10-100", "100-1000", "1000-10000", ">=10000"]
    ag([{"id": "m", "downloads": 5}])
    assert list(c.uc_hf_modeller()["indirme_dagilimi"]["histogram"]) == \
        ["<1000", "1000-100000", "100000-1e+06", "1e+06-1e+07", ">=1e+07"]


# ── page limits and the page-cap note ───────────────────────────────────────
def test_x402_stops_when_the_pages_cover_the_total(ag):
    cagrilar = ag({"pagination": {"total": 500}, "items": [{"quality": {}}] * 500})
    o = c.uc_x402()
    assert len(cagrilar) == 1 and o["sayfa"] == 1


def test_x402_total_reached_exactly_at_the_cap_has_no_cap_note(ag):
    tavan = c.X402_SAYFA_TAVANI
    cagrilar = ag({"pagination": {"total": tavan * 500}, "items": [{"quality": {}}]})
    o = c.uc_x402()
    assert len(cagrilar) == tavan and "olculemedi" not in o


def test_x402_cap_with_more_items_left_is_unmeasurable(ag):
    tavan = c.X402_SAYFA_TAVANI
    ag({"pagination": {"total": tavan * 500 + 1}, "items": [{"quality": {}}]})
    o = c.uc_x402()
    assert o["sayfa"] == tavan
    assert o["olculemedi"].startswith("page cap reached: walked %d pages" % tavan)


def test_x402_short_walk_without_total_has_no_cap_note(ag):
    ag(lambda u: {"items": [{"quality": {}}] if sayfa_no(u, "offset") < 1000 else []})
    o = c.uc_x402()
    assert o["sayfa"] == 3 and "olculemedi" not in o


def test_contest_walks_stop_at_40_pages(ag):
    cagrilar = ag({"items": [], "has_next": True})
    o = c.uc_sherlock_contests()
    assert len(cagrilar) == 40 and "olculemedi" in o
    cagrilar = ag({"data": {"audits": []}, "pagination": {"nextPage": 2}})
    o = c.uc_code4rena_audits()
    assert len(cagrilar) == 80 and "olculemedi" in o


def test_contest_walk_ending_on_page_40_has_no_cap_note(ag):
    ag(lambda u: {"items": [], "has_next": sayfa_no(u) < 40})
    assert "olculemedi" not in c.uc_sherlock_contests()
    ag(lambda u: {"data": {"audits": []}, "pagination": {"nextPage": None if sayfa_no(u) == 40 else 2}})
    assert "olculemedi" not in c.uc_code4rena_audits()


@pytest.mark.parametrize("fn,yanit,sayfa", [
    (c.uc_sherlock_contests, {"contests": []}, 0),
    (c.uc_code4rena_audits, {"data": {}}, 0),
    (c.uc_cantina_competitions, {"items": []}, 1),
])
def test_unmeasurable_summary_reports_no_items(ag, fn, yanit, sayfa):
    ag(yanit)
    o = fn()
    assert o["sayfa_ogesi"] == 0 and o["sayfa"] == sayfa and o["acik_yarisma"] is None


def test_cantina_without_end_times_reports_one_page(ag):
    ag([{"id": 1}])
    assert c.uc_cantina_competitions()["sayfa"] == 1


def test_cantina_reports_one_page(ag):
    ag([])
    assert c.uc_cantina_competitions()["sayfa"] == 1


# ── lists and rounding in summaries ─────────────────────────────────────────
def test_top_lists_hold_ten_entries(ag):
    ag({"h%d" % i: {"payout": i} for i in range(12)})
    assert len(c.uc_sherlock_leaderboard()["top10"]) == 10
    ag(lambda u: {"data": {"items": [{"username": "u", "name": str(i), "stats": {"totalUsers": i}}
                                     for i in range(12)] if sayfa_no(u, "offset") == 0 else []}})
    assert len(c.uc_apify_store()["top10"]) == 10


def test_open_entry_list_holds_ten_entries(ag):
    ag({"items": [{"id": i, "ends_at": SIMDI_EP + (i + 1) * GUN, "type_label": "Public"} for i in range(12)],
        "total": 12})
    o = c.uc_sherlock_contests()
    assert o["acik_yarisma"] == 12 and len(o["acik_kapilar"]) == 10


def test_defillama_category_rounding_and_top_five(ag):
    p = [{"name": "p%d" % i, "category": "AI Agents", "total24h": 1.234, "total30d": 1000 + i + 0.456}
         for i in range(6)]
    ag({"protocols": p})
    o = c.uc_defillama_kategori()
    assert o["ai_total24h"] == 7.4 and o["ai_total30d"] == round(sum(x["total30d"] for x in p), 2)
    assert len(o["ai_top5_30d"]) == 5 and o["ai_top5_30d"][0] == {"ad": "p5", "usd30d": 1005.46}


def test_hugging_face_values_on_a_bucket_edge_go_to_the_upper_bucket(ag):
    ag([{"id": "a", "downloads": 1000000}, {"id": "b", "downloads": 10000000}])
    h = c.uc_hf_modeller()["indirme_dagilimi"]["histogram"]
    assert h["1e+06-1e+07"] == 1 and h[">=1e+07"] == 1 and h["100000-1e+06"] == 0


def test_remaining_days_are_rounded_to_two_decimals():
    assert c._kapi("a", 1, "t", SIMDI_EP + GUN // 3, True)["kalan_gun"] == 0.33


def test_npm_with_every_day_numeric_is_measurable(ag, monkeypatch):
    monkeypatch.setattr(c, "NPM_PAKETLER", ["a"])
    ag({"downloads": [{"downloads": 1}, {"downloads": 2}]})
    assert "olculemedi" not in c.uc_npm()["a"]


# ── open-entry classification ───────────────────────────────────────────────
def test_sherlock_public_flag_per_entry(ag):
    items = [{"id": 1, "ends_at": SIMDI_EP + GUN, "type_label": "Public Audit", "private": False},
             {"id": 2, "ends_at": SIMDI_EP + GUN, "type_label": "Public Audit", "private": True},
             {"id": 3, "ends_at": SIMDI_EP + GUN, "type_label": "Public Bug Bounty", "private": False},
             {"id": 4, "ends_at": SIMDI_EP + GUN, "type_label": "Private Audit", "private": False}]
    ag({"items": items, "total": 4})
    o = c.uc_sherlock_contests()
    assert {k["id"]: k["kamu"] for k in o["acik_kapilar"]} == {1: True, 2: False, 3: False, 4: False}


def test_code4rena_open_and_public_entries(ag):
    au = [{"slug": "a", "endTime": iso(SIMDI_EP + GUN), "codeAccess": "public"},
          {"slug": "a2", "endTime": iso(SIMDI_EP + GUN), "codeAccess": "public"},
          {"slug": "b", "endTime": iso(SIMDI_EP + GUN), "codeAccess": "top_secret"},
          {"slug": "c", "endTime": iso(SIMDI_EP), "codeAccess": "public"}]
    ag({"data": {"audits": au}, "pagination": {}})
    o = c.uc_code4rena_audits()
    assert {k["id"]: k["kamu"] for k in o["acik_kapilar"]} == {"a": True, "a2": True, "b": False}
    assert o["acik_yarisma"] == 3 and o["acik_kamu"] == 2


def test_cantina_open_and_public_entries(ag):
    d = [{"id": "a", "kind": "public_contest", "timeframe": {"end": iso(SIMDI_EP + GUN)}},
         {"id": "a2", "kind": "public_contest", "timeframe": {"end": iso(SIMDI_EP + GUN)}},
         {"id": "b", "kind": "private_contest", "timeframe": {"end": iso(SIMDI_EP + GUN)}},
         {"id": "c", "kind": "public_contest", "timeframe": {"end": iso(SIMDI_EP)}}]
    ag(d)
    o = c.uc_cantina_competitions()
    assert {k["id"]: k["kamu"] for k in o["acik_kapilar"]} == {"a": True, "a2": True, "b": False}
    assert o["acik_yarisma"] == 3 and o["acik_kamu"] == 2


# ── main ────────────────────────────────────────────────────────────────────
def test_main_rounds_seconds_writes_raw_text_and_stays_quiet_when_all_ok(tmp_path, monkeypatch, capsys):
    saat = iter([0.0, 1.23456])
    monkeypatch.setattr(c.time, "time", lambda: next(saat))
    monkeypatch.setattr(c, "UCLAR", [("a", lambda: {"ad": "çğ"}, "")])
    hedef = tmp_path / "seri.ndjson"
    assert c.main(["--out", str(hedef)]) == 0
    metin = hedef.read_text(encoding="utf-8")
    assert '"ad": "çğ"' in metin and json.loads(metin)["saniye"] == 1.23
    assert "ENDPOINT MISSING" not in capsys.readouterr().out
