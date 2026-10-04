"""Tests for collector.py — every HTTP call is answered by a fake `cek`, time is frozen,
and the series path is redirected into tmp_path."""
import json
import urllib.error
from datetime import datetime, timezone

import pytest

import collector as c
import freshness_watchdog as w
from conftest import SIMDI, sabit_datetime

SIMDI_EP = int(SIMDI.timestamp())
GUN = 86400


@pytest.fixture(autouse=True)
def sabit_zaman(monkeypatch):
    monkeypatch.setattr(c.time, "time", lambda: float(SIMDI_EP))
    monkeypatch.setattr(c.time, "sleep", lambda s: None)
    monkeypatch.setattr(c, "datetime", sabit_datetime(SIMDI))


class SahteAg:
    """Routes URLs to canned responses: a dict {substring: response | callable(url) | Exception}."""
    def __init__(self, rotalar):
        self.rotalar, self.cagrilar = rotalar, []

    def __call__(self, url, ham=False):
        self.cagrilar.append(url)
        for parca, yanit in self.rotalar.items():
            if parca in url:
                if isinstance(yanit, Exception):
                    raise yanit
                return 200, (yanit(url) if callable(yanit) else yanit)
        raise AssertionError("unexpected URL: %s" % url)


@pytest.fixture
def ag(monkeypatch):
    def kur(rotalar):
        s = SahteAg(rotalar)
        monkeypatch.setattr(c, "cek", s)
        return s
    return kur


def iso(ep):
    return datetime.fromtimestamp(ep, timezone.utc).isoformat().replace("+00:00", "Z")


# ── cek ─────────────────────────────────────────────────────────────────────
class SahteYanit:
    def __init__(self, govde, status=200):
        self.govde, self.status = govde, status

    def read(self):
        return self.govde

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestCek:
    def test_json_and_headers(self, monkeypatch):
        gorulen = {}

        def sahte(req, timeout):
            gorulen.update(url=req.full_url, ua=req.get_header("User-agent"),
                           accept=req.get_header("Accept"), timeout=timeout)
            return SahteYanit(b'{"a": 1}')
        monkeypatch.setattr(c.urllib.request, "urlopen", sahte)
        assert c.cek("https://ornek.test/x") == (200, {"a": 1})
        assert gorulen == {"url": "https://ornek.test/x", "ua": c.UA,
                           "accept": "application/json", "timeout": c.ZAMAN_ASIMI}

    def test_raw(self, monkeypatch):
        monkeypatch.setattr(c.urllib.request, "urlopen", lambda req, timeout: SahteYanit(b"<html>", 203))
        assert c.cek("https://ornek.test", ham=True) == (203, b"<html>")

    def test_invalid_json_raises(self, monkeypatch):
        monkeypatch.setattr(c.urllib.request, "urlopen", lambda req, timeout: SahteYanit(b"<html>"))
        with pytest.raises(json.JSONDecodeError):
            c.cek("https://ornek.test")


# ── pure helpers ────────────────────────────────────────────────────────────
class TestYuzdelik:
    def test_empty(self):
        assert c.yuzdelik([], 50) is None

    def test_single(self):
        assert all(c.yuzdelik([7], p) == 7 for p in (0, 50, 100))

    def test_extremes(self):
        d = list(range(1, 11))
        assert c.yuzdelik(d, 0) == 1 and c.yuzdelik(d, 100) == 10

    def test_out_of_range_p_is_clamped(self):
        assert c.yuzdelik([1, 2, 3], 250) == 3 and c.yuzdelik([1, 2, 3], -50) == 1

    def test_returns_an_element_never_interpolates(self):
        d = [1, 10, 100, 1000, 10000]
        assert c.yuzdelik(d, 50) == 100 and c.yuzdelik(d, 90) == 10000 and c.yuzdelik(d, 10) == 1


class TestNearestRank:
    """Nearest-rank: the value at rank ceil(p/100 * n), 1-based."""
    @pytest.mark.parametrize("p, beklenen", [(10, 2), (25, 5), (50, 9), (75, 13), (90, 16), (95, 17), (99, 17)])
    def test_n17(self, p, beklenen):
        assert c.yuzdelik(list(range(1, 18)), p) == beklenen

    def test_no_bankers_rounding(self):
        # n=6, p=50 -> rank 3; n=4, p=50 -> rank 2
        assert c.yuzdelik([1, 2, 3, 4, 5, 6], 50) == 3 and c.yuzdelik([1, 2, 3, 4], 50) == 2

    def test_version_is_bumped_with_the_definition(self):
        assert c.SURUM == "0.4"


class TestDagilimOzeti:
    def test_empty_and_non_numeric(self):
        assert c.dagilim_ozeti([], [1]) == {"n": 0}
        assert c.dagilim_ozeti([None, "3", {}], [1]) == {"n": 0}

    def test_full_summary(self):
        o = c.dagilim_ozeti([0, 0, 5, 50, 500, None, "x"], [1, 10, 100])
        assert o["n"] == 5 and o["toplam"] == 555 and o["sifir_sayisi"] == 2 and o["maks"] == 500
        assert o["histogram"] == {"<1": 2, "1-10": 1, "10-100": 1, ">=100": 1}
        assert o["p50"] == 5 and o["p99"] == 500
        assert o["top1_pay"] == round(500 / 555, 4) and o["top10_pay"] == 1.0
        assert list(o)[:3] == ["n", "toplam", "sifir_sayisi"]

    def test_bucket_boundaries_go_up(self):
        h = c.dagilim_ozeti([1, 10, 100, 0.999], [1, 10, 100])["histogram"]
        assert h == {"<1": 1, "1-10": 1, "10-100": 1, ">=100": 1}

    def test_bucket_label_format(self):
        h = c.dagilim_ozeti([5], [100000, 1000000])["histogram"]
        assert list(h) == ["<100000", "100000-1e+06", ">=1e+06"]

    def test_histogram_counts_sum_to_n(self):
        d = [0, 1, 2, 3, 99, 100, 1e9, -5]
        assert sum(c.dagilim_ozeti(d, [1, 10, 100])["histogram"].values()) == len(d)

    def test_all_zero_has_no_concentration(self):
        o = c.dagilim_ozeti([0, 0], [1])
        assert o["toplam"] == 0 and "top1_pay" not in o and "top10_pay" not in o

    def test_duplicates_counted(self):
        o = c.dagilim_ozeti([3, 3, 3], [1])
        assert o["n"] == 3 and o["top1_pay"] == round(3 / 9, 4)

    def test_top10_uses_largest_ten(self):
        o = c.dagilim_ozeti(list(range(1, 21)), [1])
        assert o["top10_pay"] == round(sum(range(11, 21)) / 210, 4)

    def test_order_independent(self):
        assert c.dagilim_ozeti([5, 1, 3], [2]) == c.dagilim_ozeti([1, 3, 5], [2])


class TestIsoEpoch:
    @pytest.mark.parametrize("s,ep", [("2026-08-18T15:00:00Z", SIMDI_EP),
                                      ("2026-08-18T17:00:00+02:00", SIMDI_EP),
                                      ("2026-08-18T15:00:00.900Z", SIMDI_EP)])
    def test_parses(self, s, ep):
        assert c._iso_epoch(s) == ep

    @pytest.mark.parametrize("s", [None, "", "yarin", 1724000000, [], "2026-02-30T00:00:00Z"])
    def test_unparseable_is_none_not_zero(self, s):
        assert c._iso_epoch(s) is None


def test_kapi():
    k = c._kapi("sherlock", 7, "x" * 200, SIMDI_EP + 2 * GUN + GUN // 2, 1, odul=10, url="u", etiket="t")
    assert k == {"arena": "sherlock", "id": 7, "baslik": "x" * 120, "kamu": True,
                 "biter_utc": "2026-08-21T03:00:00+00:00", "kalan_gun": 2.5,
                 "odul": 10, "url": "u", "etiket": "t"}
    assert c._kapi("a", 1, None, SIMDI_EP, 0)["baslik"] == "None"


# ── endpoint collectors ─────────────────────────────────────────────────────
class TestX402:
    def test_walks_pages_until_total(self, ag):
        def sayfa(url):
            off = int(url.rsplit("=", 1)[1])
            if off == 0:
                return {"pagination": {"total": 501},
                        "items": [{"resource": "r%d" % i, "quality": {"l30DaysTotalCalls": i,
                                                                      "l30DaysUniquePayers": 1}}
                                  for i in range(500)]}
            return {"pagination": {"total": 501},
                    "items": [{"resource": "son", "quality": {"l30DaysTotalCalls": 10 ** 6}}]}
        s = ag({"x402/discovery": sayfa})
        o = c.uc_x402()
        assert [u.rsplit("=", 1)[1] for u in s.cagrilar] == ["0", "500"]
        assert o["kaynak_sayisi"] == 501 and o["taranan"] == 501 and o["sayfa"] == 2
        assert o["top10_cagri"][0] == {"cagri": 10 ** 6, "kaynak": "son"}
        assert len(o["top10_cagri"]) == 10 and o["odeyen_30g"]["n"] == 500

    def test_stops_on_empty_page_when_total_missing(self, ag):
        yan = iter([{"items": [{"quality": {"l30DaysTotalCalls": 3}}]}, {"items": []}])
        ag({"x402": lambda u: next(yan)})
        o = c.uc_x402()
        assert o["kaynak_sayisi"] is None and o["sayfa"] == 2 and o["taranan"] == 1

    def test_page_cap(self, ag):
        s = ag({"x402": {"items": [{"quality": {}}]}})
        o = c.uc_x402()
        assert len(s.cagrilar) == c.X402_SAYFA_TAVANI and o["sayfa"] == c.X402_SAYFA_TAVANI

    def test_top_level_fields_are_not_counted(self, ag):
        ag({"x402": {"pagination": {"total": 2},
                     "items": [{"l30DaysTotalCalls": 5}, {"quality": None},
                               {"quality": {"l30DaysTotalCalls": "9"}}]}})
        o = c.uc_x402()
        assert o["taranan"] == 0 and o["cagri_30g"] == {"n": 0} and o["top10_cagri"] == []

    def test_resource_truncated(self, ag):
        ag({"x402": {"pagination": {"total": 1},
                     "items": [{"resource": "u" * 300, "quality": {"l30DaysTotalCalls": 1}}]}})
        assert len(c.uc_x402()["top10_cagri"][0]["kaynak"]) == 120


class TestSherlockLeaderboard:
    def test_distribution(self, ag):
        ag({"leaderboard": {"a": {"payout": 10}, "b": {"payout": 0}, "c": {"payout": "x"},
                            "d": "bozuk", "e": {"payout": 999.5}}})
        o = c.uc_sherlock_leaderboard()
        assert o["arastirmaci_sayisi"] == 5 and o["odemeli_kayit"] == 3
        assert o["top10"] == [{"handle": "e", "odeme": 999.5}, {"handle": "a", "odeme": 10},
                              {"handle": "b", "odeme": 0}]
        assert o["omur_boyu_odeme"]["sifir_sayisi"] == 1

    def test_empty(self, ag):
        ag({"leaderboard": {}})
        o = c.uc_sherlock_leaderboard()
        assert o["arastirmaci_sayisi"] == 0 and o["omur_boyu_odeme"] == {"n": 0}

    def test_non_dict_is_reported(self, ag):
        ag({"leaderboard": [1, 2]})
        assert c.uc_sherlock_leaderboard() == {"hata": "expected a dict, got: list"}


class TestSherlockContests:
    def oge(self, i, ends, tl="Public Audit Contest", private=False):
        return {"id": i, "title": "c%d" % i, "ends_at": ends, "type_label": tl,
                "private": private, "prize_pool": 1000}

    def test_open_window_and_public_classification(self, ag):
        items = [self.oge(1, SIMDI_EP + 3 * GUN),
                 self.oge(2, SIMDI_EP + 1 * GUN, private=True),
                 self.oge(3, SIMDI_EP + 2 * GUN, tl="Public Bug Bounty"),
                 self.oge(4, SIMDI_EP + 5 * GUN, tl="Private Audit"),
                 self.oge(5, SIMDI_EP),                 # ends exactly now -> closed
                 self.oge(6, SIMDI_EP - GUN),
                 self.oge(7, None)]
        ag({"contests": {"items": items, "total": 7, "pages": 1, "has_next": False}})
        o = c.uc_sherlock_contests()
        assert o["yarisma_sayisi"] == 7 and o["sayfa_ogesi"] == 7 and o["sayfa"] == 1
        assert o["acik_yarisma"] == 4 and o["acik_kamu"] == 1
        assert [k["id"] for k in o["acik_kapilar"]] == [2, 3, 1, 4]
        assert o["acik_kapilar"][2]["url"] == "https://audits.sherlock.xyz/contests/1"

    def test_paginates(self, ag):
        def sayfa(url):
            n = int(url.rsplit("=", 1)[1])
            return {"items": [self.oge(n, SIMDI_EP + GUN)], "total": 3, "has_next": n < 3}
        s = ag({"contests": sayfa})
        o = c.uc_sherlock_contests()
        assert len(s.cagrilar) == 3 and "per_page=100" in s.cagrilar[0]
        assert o["sayfa"] == 3 and o["acik_yarisma"] == 3

    def test_list_capped(self, ag):
        items = [self.oge(i, SIMDI_EP + (i + 1) * GUN) for i in range(15)]
        ag({"contests": {"items": items, "total": 15}})
        o = c.uc_sherlock_contests()
        assert o["acik_yarisma"] == 15 and len(o["acik_kapilar"]) == c.PENCERE_LISTE_TAVANI

    @pytest.mark.parametrize("yanit", [{"contests": []}, [1], None])
    def test_missing_items_is_unmeasurable(self, ag, yanit):
        ag({"contests": yanit})
        o = c.uc_sherlock_contests()
        assert o["acik_yarisma"] is None and "olculemedi" in o and "no `items`" in o["olculemedi"]

    def test_no_numeric_ends_at_is_unmeasurable(self, ag):
        ag({"contests": {"items": [{"id": 1, "ends_at": "2026-09-01"}, {"id": 2}], "total": 2}})
        o = c.uc_sherlock_contests()
        assert o["acik_yarisma"] is None and o["yarisma_sayisi"] == 2
        assert "none of the 2 items" in o["olculemedi"]

    def test_empty_items_is_zero_open(self, ag):
        ag({"contests": {"items": [], "total": 0}})
        o = c.uc_sherlock_contests()
        assert o["acik_yarisma"] == 0 and "olculemedi" not in o


class TestCode4rena:
    def audit(self, slug, end, access="public"):
        return {"slug": slug, "title": slug, "endTime": end, "codeAccess": access,
                "formattedAmount": "$1", "auditType": "Audit"}

    def test_open_and_public(self, ag):
        au = [self.audit("a", iso(SIMDI_EP + 2 * GUN)), self.audit("b", iso(SIMDI_EP + GUN), "top_secret"),
              self.audit("c", iso(SIMDI_EP - GUN)), self.audit("d", "bozuk"), self.audit("e", None)]
        ag({"code4rena": {"data": {"audits": au}, "pagination": {"total": 5, "lastPage": 1}}})
        o = c.uc_code4rena_audits()
        assert o["acik_yarisma"] == 2 and o["acik_kamu"] == 1 and o["son_sayfa_alani"] == 1
        assert [k["id"] for k in o["acik_kapilar"]] == ["b", "a"]
        assert o["acik_kapilar"][1]["url"] == "https://code4rena.com/audits/a"

    def test_paginates_on_next_page(self, ag):
        def sayfa(url):
            n = int(url.rsplit("=", 1)[1])
            return {"data": {"audits": [self.audit("s%d" % n, iso(SIMDI_EP + GUN))]},
                    "pagination": {"total": 2, "nextPage": 2 if n == 1 else None}}
        s = ag({"code4rena": sayfa})
        assert c.uc_code4rena_audits()["sayfa"] == 2 and len(s.cagrilar) == 2

    @pytest.mark.parametrize("yanit", [{"data": {}}, {"data": {"audits": {}}}, [], None])
    def test_schema_break(self, ag, yanit):
        ag({"code4rena": yanit})
        o = c.uc_code4rena_audits()
        assert o["acik_yarisma"] is None and "data.audits" in o["olculemedi"]

    def test_unparseable_end_times(self, ag):
        ag({"code4rena": {"data": {"audits": [self.audit("a", "dun")]}, "pagination": {"total": 1}}})
        assert "parseable `endTime`" in c.uc_code4rena_audits()["olculemedi"]


class TestCantina:
    def test_open_public_and_kyc(self, ag):
        d = [{"id": "a", "name": "A", "kind": "public_contest", "kycRequired": True,
              "timeframe": {"end": iso(SIMDI_EP + GUN)}},
             {"id": "b", "kind": "private_contest", "timeframe": {"end": iso(SIMDI_EP + 2 * GUN)}},
             {"id": "c", "kind": "public_contest", "timeframe": {"end": iso(SIMDI_EP - GUN)}},
             "bozuk", {"id": "d", "timeframe": None}]
        ag({"cantina": d})
        o = c.uc_cantina_competitions()
        assert o["yarisma_sayisi"] == 5 and o["acik_yarisma"] == 2 and o["acik_kamu"] == 1
        assert o["acik_kapilar"][0]["kyc"] is True

    def test_non_list(self, ag):
        ag({"cantina": {"items": []}})
        assert "expected a list" in c.uc_cantina_competitions()["olculemedi"]

    def test_no_end_times(self, ag):
        ag({"cantina": [{"id": 1}]})
        assert c.uc_cantina_competitions()["acik_yarisma"] is None

    def test_empty_list(self, ag):
        ag({"cantina": []})
        assert c.uc_cantina_competitions()["acik_yarisma"] == 0


class TestDefillama:
    def test_category(self, ag):
        p = [{"name": "v", "category": "AI Agents", "total24h": 1, "total7d": 7, "total30d": 3000},
             {"name": "w", "category": "AI Agents", "total24h": None, "total30d": 100},
             {"name": "x", "category": "Dexs", "total30d": 10 ** 9}, {"name": "y"}]
        ag({"overview/fees": {"protocols": p}})
        o = c.uc_defillama_kategori()
        assert o["ai_agent_protokol_sayisi"] == 2 and o["toplam_protokol"] == 4
        assert o["ai_total24h"] == 1 and o["ai_total24h_n"] == 1
        assert o["ai_total7d_n"] == 1 and o["ai_total30d"] == 3100
        assert o["ai_top5_30d"] == [{"ad": "v", "usd30d": 3000.0}, {"ad": "w", "usd30d": 100.0}]
        assert o["ai_30g_dagilim"]["n"] == 2

    def test_category_empty(self, ag):
        ag({"overview/fees": {}})
        o = c.uc_defillama_kategori()
        assert o["ai_agent_protokol_sayisi"] == 0 and o["ai_total30d"] == 0

    def test_protocol(self, ag):
        tdc = [[SIMDI_EP - (40 - i) * GUN, i] for i in range(40)]
        tdc[-1][1] = None
        ag({"summary/fees/virtuals-protocol": {"name": "Virtuals", "totalDataChart": tdc,
                                               "total30d": 5, "totalAllTime": 9}})
        o = c.uc_defillama_protokol()
        assert o["protokol"] == "Virtuals" and o["gun_sayisi"] == 40 and o["total30d"] == 5
        assert o["ilk_gun_utc"] == "2026-07-09" and o["son_gun_utc"] == "2026-08-17"
        assert o["son30g_dagilim"]["n"] == 29 and o["total24h"] is None

    def test_protocol_empty_chart(self, ag):
        ag({"summary/fees": {"totalDataChart": None}})
        o = c.uc_defillama_protokol()
        assert o["gun_sayisi"] == 0 and o["ilk_gun_utc"] is None and o["son30g_dagilim"] == {"n": 0}


class TestApify:
    def test_pages_until_empty(self, ag):
        def sayfa(url):
            off = int(url.split("offset=")[1].split("&")[0])
            items = [] if off >= 200 else [{"username": "u", "name": "a%d" % off, "stats": {"totalUsers": off}},
                                          {"username": "u", "name": "nostat", "stats": None}]
            return {"data": {"total": 47744, "items": items}}
        s = ag({"apify": sayfa})
        o = c.uc_apify_store()
        assert len(s.cagrilar) == 3 and o["sayfa"] == 3
        assert o["magaza_toplam_aktor"] == 47744 and o["taranan"] == 2
        assert o["top10"][0] == {"aktor": "u/a100", "kullanici": 100}

    def test_cap_at_ten_pages(self, ag):
        s = ag({"apify": {"data": {"items": [{"stats": {"totalUsers": 1}}]}}})
        assert c.uc_apify_store()["sayfa"] == 10 and len(s.cagrilar) == 10


class TestHf:
    def test_models(self, ag):
        d = [{"id": "m%d" % i, "downloads": i * 1000, "likes": i} for i in range(12)] + [{"id": "x"}]
        ag({"huggingface": d})
        o = c.uc_hf_modeller()
        assert o["model_sayisi"] == 13 and o["indirme_dagilimi"]["n"] == 12
        assert len(o["top10"]) == 10 and o["top10"][0] == {"id": "m0", "indirme": 0, "begeni": 0}

    def test_non_list(self, ag):
        ag({"huggingface": {"error": "x"}})
        assert c.uc_hf_modeller() == {"hata": "expected a list"}


class TestPackageEndpoints:
    def test_npm(self, ag, monkeypatch):
        monkeypatch.setattr(c, "NPM_PAKETLER", ["@anthropic-ai/sdk", "bozuk", "bos"])
        s = ag({"%40anthropic-ai%2Fsdk": {"start": "a", "end": "b",
                                         "downloads": [{"downloads": 5}, {"day": "x"}, {"downloads": 7}]},
                "/bozuk": RuntimeError("down"),
                "/bos": {}})
        o = c.uc_npm()
        assert o["@anthropic-ai/sdk"] == {"baslangic": "a", "bitis": "b", "gun": 3, "toplam_30g": 12,
                                          "son_gun": {"downloads": 7},
                                          "olculemedi": "1 of 3 day records have no numeric downloads"}
        assert o["bozuk"] == {"hata": "RuntimeError('down')"}
        assert o["bos"]["toplam_30g"] == 0 and o["bos"]["son_gun"] is None
        assert len(s.cagrilar) == 3

    def test_pypi(self, ag, monkeypatch):
        monkeypatch.setattr(c, "PYPI_PAKETLER", ["anthropic", "kotu"])
        veri = ([{"category": "with_mirrors", "date": "d00", "downloads": 10 ** 6}]
                + [{"category": "without_mirrors", "date": "d%02d" % i, "downloads": 1} for i in range(1, 41)])
        ag({"anthropic": {"data": veri}, "kotu": urllib.error.URLError("x")})
        o = c.uc_pypi()
        assert o["anthropic"] == {"kayit": 41, "aynasiz_gun": 40, "ilk_tarih": "d00", "son_tarih": "d40",
                                  "aynasiz_toplam": 40, "aynasiz_son30g": 30}
        assert "hata" in o["kotu"]

    def test_github(self, ag, monkeypatch):
        monkeypatch.setattr(c, "GH_DEPOLAR", ["a/b", "c/d"])
        ag({"repos/a/b": {"stargazers_count": 3, "forks_count": 1, "subscribers_count": 2,
                          "open_issues_count": 0, "pushed_at": "t"},
            "repos/c/d": urllib.error.HTTPError("u", 403, "rate", None, None)})
        o = c.uc_github()
        assert o["a/b"] == {"yildiz": 3, "catal": 1, "izleyen": 2, "acik_konu": 0, "son_push": "t"}
        assert "403" in o["c/d"]["hata"]


# ── main ────────────────────────────────────────────────────────────────────
class TestMain:
    def kur(self, monkeypatch, tmp_path, uclar):
        seri = tmp_path / "seri.ndjson"
        monkeypatch.setattr(c, "SERI", seri)
        monkeypatch.setattr(c, "UCLAR", uclar)
        return seri

    def oku(self, seri):
        return [json.loads(x) for x in seri.read_text(encoding="utf-8").splitlines()]

    def test_status_per_failure_mode(self, monkeypatch, tmp_path, capsys):
        def http():
            raise urllib.error.HTTPError("u", 503, "x", None, None)

        def patla():
            raise ValueError("ç" * 300)
        seri = self.kur(monkeypatch, tmp_path, [
            ("ok", lambda: {"n": 1}, "not-ok"),
            ("ic", lambda: {"hata": "expected a list"}, "n"),
            ("liste", lambda: [1, 2], "n"),
            ("http", http, "n"),
            ("hata", patla, "n"),
        ])
        assert c.main() == c.KISMI
        r = {k["uc"]: k for k in self.oku(seri)}
        assert [k["uc"] for k in self.oku(seri)] == ["ok", "ic", "liste", "http", "hata"]
        assert r["ok"] == {"zaman_utc": SIMDI.isoformat(timespec="seconds"), "surum": c.SURUM, "uc": "ok",
                           "not": "not-ok", "ozet": {"n": 1}, "durum": "OK", "saniye": 0.0}
        assert r["ic"]["durum"] == "HATA-ICERIDE" and r["liste"]["durum"] == "OK"
        assert r["http"]["durum"] == "HTTP-HATA" and r["http"]["http"] == 503 and "ozet" not in r["http"]
        assert r["hata"]["durum"] == "HATA" and len(r["hata"]["hata"]) == 200
        assert "2/5 endpoints OK" in capsys.readouterr().out

    def test_appends_and_shares_one_timestamp(self, monkeypatch, tmp_path, capsys):
        seri = self.kur(monkeypatch, tmp_path, [("a", lambda: {}, ""), ("b", lambda: {}, "")])
        seri.write_text('{"onceki": 1}\n', encoding="utf-8")
        c.main()
        satirlar = seri.read_text(encoding="utf-8").splitlines()
        assert satirlar[0] == '{"onceki": 1}' and len(satirlar) == 3
        assert len({json.loads(x)["zaman_utc"] for x in satirlar[1:]}) == 1

    def test_all_failing_exits_1(self, monkeypatch, tmp_path, capsys):
        def patla():
            raise OSError("x")
        self.kur(monkeypatch, tmp_path, [("a", patla, "")])
        assert c.main() == 1
        assert "ENDPOINT MISSING" in capsys.readouterr().out

    def test_empty_endpoint_list(self, monkeypatch, tmp_path, capsys):
        seri = self.kur(monkeypatch, tmp_path, [])
        assert c.main() == 1 and seri.read_text(encoding="utf-8") == ""

    def test_output_is_green_for_the_watchdog(self, monkeypatch, tmp_path, capsys):
        uclar = [(uc, (lambda o=o: o), "") for uc, o in w._SAGLAM.items()]
        seri = self.kur(monkeypatch, tmp_path, uclar)
        assert c.main() == 0
        kod, r = w.denetle(seri, SIMDI)
        assert kod == 0, r["findings"]


def test_endpoint_registry_is_consistent():
    adlar = [u[0] for u in c.UCLAR]
    assert len(adlar) == len(set(adlar))
    assert set(w.TASIYICILAR) <= set(adlar)
    assert all(callable(u[1]) and u[2] for u in c.UCLAR)


class TestNewestStart:
    """Open-window endpoints record when their newest listed entry started."""
    def test_sherlock(self, ag):
        items = [{"id": 1, "ends_at": SIMDI_EP - GUN, "starts_at": SIMDI_EP - 40 * GUN},
                 {"id": 2, "ends_at": SIMDI_EP - GUN, "starts_at": SIMDI_EP - 10 * GUN},
                 {"id": 3, "ends_at": SIMDI_EP - GUN, "starts_at": None}]
        ag({"contests": {"items": items, "total": 3}})
        assert c.uc_sherlock_contests()["en_yeni_baslangic_utc"] == "2026-08-08T15:00:00+00:00"

    def test_code4rena(self, ag):
        au = [{"slug": "a", "endTime": iso(SIMDI_EP - GUN), "startTime": iso(SIMDI_EP - 3 * GUN)},
              {"slug": "b", "endTime": iso(SIMDI_EP - GUN), "startTime": "bozuk"}]
        ag({"code4rena": {"data": {"audits": au}, "pagination": {"total": 2}}})
        assert c.uc_code4rena_audits()["en_yeni_baslangic_utc"] == "2026-08-15T15:00:00+00:00"

    def test_cantina(self, ag):
        ag({"cantina": [{"id": "a", "timeframe": {"start": iso(SIMDI_EP - 2 * GUN),
                                                  "end": iso(SIMDI_EP - GUN)}}]})
        assert c.uc_cantina_competitions()["en_yeni_baslangic_utc"] == "2026-08-16T15:00:00+00:00"

    def test_no_start_times_is_none(self, ag):
        ag({"contests": {"items": [{"id": 1, "ends_at": SIMDI_EP - GUN}], "total": 1}})
        assert c.uc_sherlock_contests()["en_yeni_baslangic_utc"] is None


class TestCollectorId:
    """Rows carry `toplayici` when AI_ARZ_TOPLAYICI is set, so two collectors can be told apart."""
    def kur(self, monkeypatch, tmp_path):
        seri = tmp_path / "seri.ndjson"
        monkeypatch.setattr(c, "SERI", seri)
        monkeypatch.setattr(c, "UCLAR", [("a", lambda: {"n": 1}, "")])
        return seri

    def test_set(self, monkeypatch, tmp_path, capsys):
        seri = self.kur(monkeypatch, tmp_path)
        monkeypatch.setenv("AI_ARZ_TOPLAYICI", "vps-1")
        c.main()
        assert json.loads(seri.read_text(encoding="utf-8"))["toplayici"] == "vps-1"

    @pytest.mark.parametrize("deger", [None, "", "   "])
    def test_unset_or_blank_is_absent(self, monkeypatch, tmp_path, capsys, deger):
        seri = self.kur(monkeypatch, tmp_path)
        if deger is None:
            monkeypatch.delenv("AI_ARZ_TOPLAYICI", raising=False)
        else:
            monkeypatch.setenv("AI_ARZ_TOPLAYICI", deger)
        c.main()
        assert "toplayici" not in json.loads(seri.read_text(encoding="utf-8"))

    def test_truncated(self, monkeypatch, tmp_path, capsys):
        seri = self.kur(monkeypatch, tmp_path)
        monkeypatch.setenv("AI_ARZ_TOPLAYICI", "x" * 100)
        c.main()
        assert len(json.loads(seri.read_text(encoding="utf-8"))["toplayici"]) == 40


class TestNestedErrorStatus:
    """A per-package error inside the summary makes the row HATA-ICERIDE, not OK."""
    def test_nested_package_error(self, monkeypatch, tmp_path, capsys):
        seri = tmp_path / "seri.ndjson"
        monkeypatch.setattr(c, "SERI", seri)
        monkeypatch.setattr(c, "UCLAR", [
            ("paket", lambda: {"a": {"toplam_30g": 5}, "b": {"hata": "HTTPError 429"}}, ""),
            ("temiz", lambda: {"a": {"toplam_30g": 5}}, "")])
        assert c.main() == c.KISMI
        r = {json.loads(x)["uc"]: json.loads(x) for x in seri.read_text(encoding="utf-8").splitlines()}
        assert r["paket"]["durum"] == "HATA-ICERIDE" and r["temiz"]["durum"] == "OK"



class TestExitCodes:
    def kur(self, monkeypatch, tmp_path, uclar):
        monkeypatch.setattr(c, "SERI", tmp_path / "seri.ndjson")
        monkeypatch.setattr(c, "UCLAR", uclar)

    def test_all_ok_is_0(self, monkeypatch, tmp_path, capsys):
        self.kur(monkeypatch, tmp_path, [("a", lambda: {}, ""), ("b", lambda: {}, "")])
        assert c.main() == 0

    def test_partial_is_3(self, monkeypatch, tmp_path, capsys):
        def patla():
            raise OSError("x")
        self.kur(monkeypatch, tmp_path, [("a", lambda: {}, ""), ("b", patla, "")])
        assert c.main() == c.KISMI == 3

    def test_none_ok_is_1(self, monkeypatch, tmp_path, capsys):
        self.kur(monkeypatch, tmp_path, [("a", lambda: {"hata": "x"}, "")])
        assert c.main() == 1



class TestCapsAndMissingValues:
    """Hitting a page cap, or a day record without a number, is recorded as olculemedi."""
    def test_x402_cap_reached_is_unmeasurable(self, ag, monkeypatch):
        monkeypatch.setattr(c, "X402_SAYFA_TAVANI", 2)
        ag({"x402": {"pagination": {"total": 5000}, "items": [{"quality": {"l30DaysTotalCalls": 1}}]}})
        o = c.uc_x402()
        assert o["sayfa"] == 2 and "page cap" in o["olculemedi"] and "5000" in o["olculemedi"]

    def test_x402_complete_walk_has_no_olculemedi(self, ag):
        ag({"x402": {"pagination": {"total": 1}, "items": [{"quality": {"l30DaysTotalCalls": 1}}]}})
        assert "olculemedi" not in c.uc_x402()

    def test_sherlock_cap_reached_is_unmeasurable(self, ag, monkeypatch):
        monkeypatch.setattr(c, "YARISMA_SAYFA_TAVANI", 2)
        ag({"contests": {"items": [{"id": 1, "ends_at": SIMDI_EP - GUN}], "total": 900, "has_next": True}})
        o = c.uc_sherlock_contests()
        assert o["sayfa"] == 2 and "page cap" in o["olculemedi"]

    def test_code4rena_cap_reached_is_unmeasurable(self, ag, monkeypatch):
        monkeypatch.setattr(c, "YARISMA_SAYFA_TAVANI", 2)
        ag({"code4rena": {"data": {"audits": [{"slug": "a", "endTime": iso(SIMDI_EP - GUN)}]},
                          "pagination": {"total": 900, "nextPage": 9}}})
        o = c.uc_code4rena_audits()
        assert o["sayfa"] == 2 and "page cap" in o["olculemedi"]

    def test_pypi_row_without_downloads(self, ag, monkeypatch):
        monkeypatch.setattr(c, "PYPI_PAKETLER", ["p"])
        ag({"/p/": {"data": [{"category": "without_mirrors", "date": "d1", "downloads": 3},
                             {"category": "without_mirrors", "date": "d2"}]}})
        o = c.uc_pypi()["p"]
        assert o["aynasiz_toplam"] == 3 and o["olculemedi"] == "1 of 2 non-mirror rows have no numeric downloads"

    def test_nested_olculemedi_is_red_in_the_watchdog(self, tmp_path):
        son = dict(w._SAGLAM)
        son["npm_downloads"] = {"pkg": {"toplam_30g": 115914002, "olculemedi": "1 of 30 day records"}}
        p = tmp_path / "s.ndjson"
        satir = lambda t, u, o: json.dumps({"zaman_utc": t, "uc": u, "ozet": o, "durum": "OK"})
        p.write_text("".join(satir(SIMDI.isoformat(), u, o) + "\n" for u, o in son.items()), encoding="utf-8")
        kod, r = w.denetle(p, SIMDI)
        assert kod == 2 and any("UNMEASURABLE: npm_downloads" in b and "pkg" in b for b in r["findings"])


def test_pypi_rows_are_ordered_by_date(ag, monkeypatch):
    monkeypatch.setattr(c, "PYPI_PAKETLER", ["p"])
    veri = [{"category": "without_mirrors", "date": "2026-01-%02d" % g, "downloads": g} for g in range(31, 0, -1)]
    ag({"/p/": {"data": veri}})
    o = c.uc_pypi()["p"]
    assert o["ilk_tarih"] == "2026-01-01" and o["son_tarih"] == "2026-01-31"
    assert o["aynasiz_son30g"] == sum(range(2, 32))
