"""Cross-field checks on the published series: values inside one row that must agree with each
other. Only rows with durum == "OK" and no `olculemedi` are checked, except that every OK x402 row
is checked for whether its walk covered the registry; per-package entries that carry `hata` or
`olculemedi` are skipped. The file is only read."""
import collections
import json
from datetime import datetime, timedelta

import pytest

from conftest import KOK

SATIRLAR = [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()
            if x.strip()]
KOSU_SURESI = collections.defaultdict(float)
for _r in SATIRLAR:
    KOSU_SURESI[_r["zaman_utc"]] += _r.get("saniye") or 0


def kullanilir(uc):
    out = [r for r in SATIRLAR if r.get("uc") == uc and r.get("durum") == "OK"
           and isinstance(r.get("ozet"), dict) and "olculemedi" not in r["ozet"]]
    return pytest.mark.parametrize("r", out, ids=[r["zaman_utc"] for r in out])


def zaman(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def azalan(x):
    return x == sorted(x, reverse=True)


def paketler(r, alan):
    return [(p, v) for p, v in r["ozet"].items()
            if isinstance(v, dict) and alan in v and "hata" not in v and "olculemedi" not in v]


X402 = [r for r in SATIRLAR if r.get("uc") == "x402_discovery" and r.get("durum") == "OK"
        and isinstance(r.get("ozet"), dict)]

# A capped x402 row published without `olculemedi`; README "Known limits" describes it.
X402_KAPSAMSIZ_ISARETSIZ = {"2026-10-05T07:00:02+00:00"}


@pytest.mark.parametrize("r", X402, ids=[r["zaman_utc"] for r in X402])
def test_x402(r):
    o = r["ozet"]
    if "cagri_30g" not in o:
        return
    for alan in ("kaynak_sayisi", "sayfa"):
        deger = o.get(alan)
        assert type(deger) is int, "x402 %s must be an integer, got %r" % (alan, deger)
    kapsadi = o["sayfa"] * 500 >= o["kaynak_sayisi"]      # the walk covered the registry
    if kapsadi:
        assert o["taranan"] <= o["kaynak_sayisi"] <= o["sayfa"] * 500
    else:
        assert "olculemedi" in o or r["zaman_utc"] in X402_KAPSAMSIZ_ISARETSIZ, \
            "x402 walked %d pages for %d resources without olculemedi" % (o["sayfa"], o["kaynak_sayisi"])
        assert o["taranan"] <= o["sayfa"] * 500 < o["kaynak_sayisi"]
    assert o["cagri_30g"]["n"] == o["taranan"] and o["odeyen_30g"]["n"] <= o["taranan"]
    top = [x["cagri"] for x in o["top10_cagri"]]
    assert azalan(top) and len(top) == min(10, o["taranan"])
    assert not top or round(top[0], 2) == o["cagri_30g"]["maks"]


def test_the_listed_x402_exception_is_a_capped_row_without_olculemedi():
    satirlar = {r["zaman_utc"]: r["ozet"] for r in X402}
    for t in X402_KAPSAMSIZ_ISARETSIZ:
        if t in satirlar:
            o = satirlar[t]
            assert o["sayfa"] * 500 < o["kaynak_sayisi"] and "olculemedi" not in o


@kullanilir("sherlock_leaderboard")
def test_sherlock_leaderboard(r):
    o = r["ozet"]
    if "omur_boyu_odeme" not in o:
        return
    assert o["odemeli_kayit"] == o["omur_boyu_odeme"]["n"] <= o["arastirmaci_sayisi"]
    top = [x["odeme"] for x in o["top10"]]
    assert azalan(top) and len(top) == min(10, o["odemeli_kayit"])
    assert round(top[0], 2) == o["omur_boyu_odeme"]["maks"]


ACIK = [r for uc in ("sherlock_contests", "code4rena_audits", "cantina_competitions") for r in SATIRLAR
        if r.get("uc") == uc and r.get("durum") == "OK" and isinstance(r.get("ozet"), dict)
        and "olculemedi" not in r["ozet"] and "acik_yarisma" in r["ozet"]]


@pytest.mark.parametrize("r", ACIK, ids=["%s:%s" % (r["zaman_utc"], r["uc"]) for r in ACIK])
def test_open_entries(r):
    o, t = r["ozet"], zaman(r["zaman_utc"])
    kapilar = o["acik_kapilar"]
    assert o["acik_kamu"] <= o["acik_yarisma"] <= o["sayfa_ogesi"]
    assert o["yarisma_sayisi"] is None or o["yarisma_sayisi"] >= o["sayfa_ogesi"]
    assert len(kapilar) == min(o["acik_yarisma"], 10)
    kalan = [k["kalan_gun"] for k in kapilar]
    assert kalan == sorted(kalan)
    for k in kapilar:
        # kalan_gun is counted from the moment the endpoint was read, which lies between the run
        # start (zaman_utc) and the run end; it is rounded to two decimals
        assert zaman(k["biter_utc"]) > t
        assert abs((zaman(k["biter_utc"]) - t).total_seconds() / 86400 - k["kalan_gun"]) <= 0.005 + \
            KOSU_SURESI[r["zaman_utc"]] / 86400
    if o["acik_yarisma"] <= 10:
        assert sum(1 for k in kapilar if k["kamu"]) == o["acik_kamu"]


@kullanilir("apify_store")
def test_apify(r):
    o = r["ozet"]
    if "toplam_kullanici_dagilimi" not in o:
        return
    assert o["taranan"] == o["toplam_kullanici_dagilimi"]["n"] <= o["sayfa"] * 100
    top = [x["kullanici"] for x in o["top10"]]
    assert azalan(top) and len(top) == min(10, o["taranan"])
    assert round(top[0], 2) == o["toplam_kullanici_dagilimi"]["maks"]


@kullanilir("hf_models")
def test_hugging_face(r):
    o = r["ozet"]
    if "indirme_dagilimi" not in o:
        return
    assert o["indirme_dagilimi"]["n"] <= o["model_sayisi"]
    top = [x["indirme"] for x in o["top10"]]
    assert azalan(top) and len(top) == min(10, o["model_sayisi"])


@kullanilir("defillama_fees_ai_agents")
def test_defillama_category(r):
    o = r["ozet"]
    if "ai_30g_dagilim" not in o:
        return
    assert o["ai_agent_protokol_sayisi"] <= o["toplam_protokol"]
    assert all(o["ai_%s_n" % a] <= o["ai_agent_protokol_sayisi"] for a in ("total24h", "total7d", "total30d"))
    assert o["ai_30g_dagilim"]["n"] == o["ai_total30d_n"]
    assert o["ai_30g_dagilim"]["toplam"] == o["ai_total30d"]
    assert o["ai_total24h"] <= o["ai_total7d"] <= o["ai_total30d"]
    top = [x["usd30d"] for x in o["ai_top5_30d"]]
    assert azalan(top) and len(top) == min(5, o["ai_total30d_n"])
    assert round(top[0], 2) == o["ai_30g_dagilim"]["maks"]


@kullanilir("defillama_summary_virtuals")
def test_defillama_protocol(r):
    o = r["ozet"]
    if "son30g_dagilim" not in o:
        return
    assert o["son30g_dagilim"]["n"] <= 30
    assert o["total24h"] <= o["total7d"] <= o["total30d"] <= o["totalAllTime"]
    assert o["ilk_gun_utc"] <= o["son_gun_utc"] <= r["zaman_utc"][:10]


@kullanilir("npm_downloads")
def test_npm(r):
    for p, v in paketler(r, "toplam_30g"):
        assert v["gun"] <= 31, p
        assert v["baslangic"] <= v["bitis"] <= r["zaman_utc"][:10], p
        assert v["son_gun"] is None or v["son_gun"]["downloads"] <= v["toplam_30g"], p


@kullanilir("pypi_downloads")
def test_pypi(r):
    for p, v in paketler(r, "aynasiz_toplam"):
        assert v["aynasiz_son30g"] <= v["aynasiz_toplam"], p
        assert v["aynasiz_gun"] <= v["kayit"], p
        assert v["ilk_tarih"] <= v["son_tarih"] <= r["zaman_utc"][:10], p


@kullanilir("github_repos")
def test_github(r):
    bitis = zaman(r["zaman_utc"]) + timedelta(seconds=KOSU_SURESI[r["zaman_utc"]])
    for p, v in paketler(r, "yildiz"):
        assert all(type(v[k]) is int and v[k] >= 0 for k in ("yildiz", "catal", "izleyen", "acik_konu")), p
        assert v["son_push"] is None or zaman(v["son_push"]) <= bitis, p      # pushed before the run ended
