#!/usr/bin/env python3
"""AI-EKONOMISI ARZ-TARAFI TOPLAYICI — haftalik anlik-goruntu.  s189-T2 · v0.2

Neden: AI ekonomisinde "kim ne kazaniyor" sorusunu kimse sistematik olcmuyor
(Anthropic Economic Index TALEP/kullanim tarafini olcuyor). Bu uclarin bir kismi
GECMISI SAKLAMIYOR -> bugun alinmayan kayit geri uretilemez.

Desen kaynagi: scripts/forecast/metaculus_cp_pull.py (115 sat, dis API -> ndjson).
Kimlik dogrulama YOK. Salt-okuma. Yazdigi tek yer: kendi seri dosyasi.

v0.2 DEGISIKLIKLERI (2026-08-18, DEVIR §9-4 + §5-6 bosluk kapatma):
  1. 4 uc -> 10 uc (E11'de canli-test edilip kimlik-gerektirmedigi dogrulanan uclar).
  2. 🔴 KOK DUZELTME: v0.1 yalniz TOPLAM sayiyor, DAGILIMI atiyordu. Ama bulgunun
     kendisi dagilimda ("%94,1'i $1 altinda", "omur-boyu medyan $459"). Yani
     toplayici da "canlilik olcup uretim olcmeme" hatasini yapiyordu.
     -> x402 ve Sherlock icin artik YUZDELIK + HISTOGRAM + TOP-10 arsivleniyor.
  3. Her ucun sekli 2026-08-18'de CANLI olculdu (probe.py/probe2.py) — tahmin yok.

BILINCLI OLARAK EKLENMEYENLER (kural-10 sinir beyani):
  - layoffs.fyi /api/annual-stats : tam backend URL'i E11'de kayitli degil (olculmedi).
  - Gumroad urun-sayfasi HTML     : kirilgan scrape, urun URL'i onceden bilinmeli.
  - Replicate model sayfasi HTML  : kirilgan scrape, tek kumulatif sayi.
  Ucu de "yapilamaz" degil "bu turda olculmedi" — tetik: HTML-scrape gerekirse.
"""
import json, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
SERI = KOK / "ai-arz-serisi.ndjson"
UA = "Mozilla/5.0 (compatible; mergen-arz-olcum/0.2)"
ZAMAN_ASIMI = 30
SURUM = "0.2"

NPM_PAKETLER = ["@anthropic-ai/sdk", "openai", "langchain", "@langchain/core",
                "ai", "@modelcontextprotocol/sdk"]
PYPI_PAKETLER = ["anthropic", "openai", "langchain", "crewai"]
GH_DEPOLAR = ["langchain-ai/langchain", "anthropics/anthropic-sdk-python",
              "crewAIInc/crewAI", "modelcontextprotocol/servers",
              "Significant-Gravitas/AutoGPT"]
LLAMA_PROTOKOL = "virtuals-protocol"   # AI-Agents kategorisinin %89,7'si
X402_SAYFA_TAVANI = 60                 # 60*500 = 30.000 kaynak; guvenlik freni


# ---------------------------------------------------------------- yardimcilar
def cek(url, ham=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=ZAMAN_ASIMI) as r:
        b = r.read()
        return (r.status, b) if ham else (r.status, json.loads(b))


def yuzdelik(dizi, p):
    """Lineer-interpolasyonsuz, en-yakin-siralama yuzdeligi. dizi SIRALI olmali."""
    if not dizi:
        return None
    k = int(round((len(dizi) - 1) * p / 100.0))
    return dizi[max(0, min(k, len(dizi) - 1))]


def dagilim_ozeti(degerler, kovalar):
    """Sayi listesinden arsivlenebilir kompakt ozet: n, toplam, yuzdelikler, histogram."""
    d = sorted(float(x) for x in degerler if isinstance(x, (int, float)))
    if not d:
        return {"n": 0}
    o = {"n": len(d), "toplam": round(sum(d), 2), "sifir_sayisi": sum(1 for x in d if x == 0)}
    for p in (10, 25, 50, 75, 90, 95, 99):
        o["p%d" % p] = round(yuzdelik(d, p), 4)
    o["maks"] = round(d[-1], 2)
    hist, onceki = {}, None
    for esik in kovalar:
        ad = ("<%g" % esik) if onceki is None else ("%g-%g" % (onceki, esik))
        hist[ad] = sum(1 for x in d if (x < esik) if (onceki is None or x >= onceki))
        onceki = esik
    hist[">=%g" % kovalar[-1]] = sum(1 for x in d if x >= kovalar[-1])
    o["histogram"] = hist
    # yogunlasma: en buyuk 1'in ve en buyuk 10'un toplamdaki payi
    if o["toplam"] > 0:
        o["top1_pay"] = round(d[-1] / o["toplam"], 4)
        o["top10_pay"] = round(sum(d[-10:]) / o["toplam"], 4)
    return o


# ------------------------------------------------------------------- toplayici
def uc_x402():
    """TUM sayfalari gez, kaynak-basina 30-gunluk cagri/odeyen DAGILIMINI arsivle.
    Sekil: {items:[{resource,l30DaysTotalCalls,l30DaysUniquePayers,...}], pagination:{total}}
    ROLLING 30-GUN PENCERESI: gecmis yok, bugun alinmayan geri uretilemez."""
    tab = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=500&offset=%d"
    cagri, odeyen, toplam, sayfa = [], [], None, 0
    ilk_uc = []
    while sayfa < X402_SAYFA_TAVANI:
        _, d = cek(tab % (sayfa * 500))
        ogeler = d.get("items", [])
        if toplam is None:
            toplam = d.get("pagination", {}).get("total")
        for it in ogeler:
            # 🔴 OLCULDU 2026-08-18: alanlar UST duzeyde DEGIL, it["quality"] altinda.
            # v0.2 ilk yaziminda ust duzeyde arandi -> 151 sayfa gezip 0 deger topladi
            # (exit=0 + sifir satir tuzagi, kural-12f). Kuru-kosuda yakalandi, veriye yazilmadi.
            q = it.get("quality") or {}
            c = q.get("l30DaysTotalCalls")
            o = q.get("l30DaysUniquePayers")
            if isinstance(c, (int, float)):
                cagri.append(c)
                ilk_uc.append((c, str(it.get("resource"))[:120]))
            if isinstance(o, (int, float)):
                odeyen.append(o)
        sayfa += 1
        if not ogeler or (toplam is not None and sayfa * 500 >= toplam):
            break
        time.sleep(0.25)
    ilk_uc.sort(key=lambda x: -x[0])
    return {"kaynak_sayisi": toplam, "taranan": len(cagri), "sayfa": sayfa,
            "cagri_30g": dagilim_ozeti(cagri, [1, 10, 100, 1000, 10000]),
            "odeyen_30g": dagilim_ozeti(odeyen, [1, 2, 5, 10, 100]),
            "top10_cagri": [{"cagri": c, "kaynak": r} for c, r in ilk_uc[:10]]}


def uc_sherlock_leaderboard():
    """Sekil: {handle: {payout, score, ranking, ...}} — KUMULATIF, tarih parametresi YOK.
    v0.1 yalniz sayiyordu; asil bulgu OMUR-BOYU KAZANC DAGILIMINDA."""
    _, d = cek("https://mainnet-contest.sherlock.xyz/stats/leaderboard")
    if not isinstance(d, dict):
        return {"hata": "beklenen dict degil: %s" % type(d).__name__}
    odeme, en_iyi = [], []
    for h, v in d.items():
        if isinstance(v, dict):
            p = v.get("payout")
            if isinstance(p, (int, float)):
                odeme.append(p)
                en_iyi.append((p, h))
    en_iyi.sort(key=lambda x: -x[0])
    return {"arastirmaci_sayisi": len(d),
            "odemeli_kayit": len(odeme),
            "omur_boyu_odeme": dagilim_ozeti(odeme, [1, 100, 1000, 10000, 100000]),
            "top10": [{"handle": h, "odeme": p} for p, h in en_iyi[:10]]}


def uc_sherlock_contests():
    _, d = cek("https://mainnet-contest.sherlock.xyz/contests")
    return {"yarisma_sayisi": d.get("total"), "sayfa_ogesi": len(d.get("items", []))}


def uc_defillama_kategori():
    _, d = cek("https://api.llama.fi/overview/fees"
               "?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true")
    p = d.get("protocols", [])
    ai = [x for x in p if "AI Agent" in str(x.get("category", ""))]
    o = {"ai_agent_protokol_sayisi": len(ai), "toplam_protokol": len(p)}
    for alan in ("total24h", "total7d", "total30d"):
        v = [x[alan] for x in ai if isinstance(x.get(alan), (int, float))]
        o["ai_" + alan] = round(sum(v), 2)
        o["ai_" + alan + "_n"] = len(v)
    ilk = sorted([x for x in ai if isinstance(x.get("total30d"), (int, float))],
                 key=lambda x: -x["total30d"])[:5]
    o["ai_top5_30d"] = [{"ad": x.get("name"), "usd30d": round(float(x["total30d"]), 2)} for x in ilk]
    o["ai_30g_dagilim"] = dagilim_ozeti(
        [x.get("total30d") for x in ai], [100, 1000, 10000, 100000])
    return o


def uc_defillama_protokol():
    """Tek protokolun GUNLUK gelir serisi (~671 gun arsivli). Yogunlasmanin merkezi."""
    _, d = cek("https://api.llama.fi/summary/fees/%s" % LLAMA_PROTOKOL)
    tdc = d.get("totalDataChart") or []
    son30 = [v for _, v in tdc[-30:] if isinstance(v, (int, float))]
    return {"protokol": d.get("name"), "gun_sayisi": len(tdc),
            "total24h": d.get("total24h"), "total7d": d.get("total7d"),
            "total30d": d.get("total30d"), "totalAllTime": d.get("totalAllTime"),
            "ilk_gun_utc": (datetime.fromtimestamp(tdc[0][0], timezone.utc).date().isoformat()
                            if tdc else None),
            "son_gun_utc": (datetime.fromtimestamp(tdc[-1][0], timezone.utc).date().isoformat()
                            if tdc else None),
            "son30g_dagilim": dagilim_ozeti(son30, [1000, 10000, 100000])}


def uc_apify_store():
    """Sekil: {data:{total,count,items:[{name,username,stats:{totalUsers,...}}]}}
    E5 bulgusu 'medyan 2 kullanici' idi — o bulgunun CANLI izlenmesi."""
    tab = "https://api.apify.com/v2/store?limit=100&offset=%d&sortBy=popularity"
    kullanici, toplam, sayfa, en_iyi = [], None, 0, []
    while sayfa < 10:                      # 1.000 aktor: populerlik-sirali ust dilim
        _, d = cek(tab % (sayfa * 100))
        veri = d.get("data", {})
        ogeler = veri.get("items", [])
        if toplam is None:
            toplam = veri.get("total")
        for it in ogeler:
            s = it.get("stats", {}) or {}
            tu = s.get("totalUsers")
            if isinstance(tu, (int, float)):
                kullanici.append(tu)
                en_iyi.append((tu, "%s/%s" % (it.get("username"), it.get("name"))))
        sayfa += 1
        if not ogeler:
            break
        time.sleep(0.25)
    en_iyi.sort(key=lambda x: -x[0])
    return {"magaza_toplam_aktor": toplam, "taranan": len(kullanici), "sayfa": sayfa,
            "kapsam_notu": "populerlik-sirali ILK 1000 (ust dilim) — magaza medyani DEGIL",
            "toplam_kullanici_dagilimi": dagilim_ozeti(kullanici, [1, 10, 100, 1000, 10000]),
            "top10": [{"aktor": a, "kullanici": k} for k, a in en_iyi[:10]]}


def uc_hf_modeller():
    """Kumulatif indirme — resmi TARIHSEL uc YOK. Arsivleyen biziz."""
    _, d = cek("https://huggingface.co/api/models?sort=downloads&direction=-1&limit=100")
    if not isinstance(d, list):
        return {"hata": "beklenen list degil"}
    ind = [x.get("downloads") for x in d if isinstance(x.get("downloads"), (int, float))]
    return {"model_sayisi": len(d),
            "indirme_dagilimi": dagilim_ozeti(ind, [1000, 100000, 1000000, 10000000]),
            "top10": [{"id": x.get("id"), "indirme": x.get("downloads"), "begeni": x.get("likes")}
                      for x in d[:10]]}


def uc_npm():
    """Sunucu istenen araligi ~547 gune kirpiyor -> ESKI VERI DUSUYOR. Arsivle."""
    cikti = {}
    for pkt in NPM_PAKETLER:
        try:
            _, d = cek("https://api.npmjs.org/downloads/range/last-month/%s"
                       % urllib.parse.quote(pkt, safe=""))
            gunler = d.get("downloads", [])
            cikti[pkt] = {"baslangic": d.get("start"), "bitis": d.get("end"),
                          "gun": len(gunler),
                          "toplam_30g": sum(g.get("downloads", 0) for g in gunler),
                          "son_gun": gunler[-1] if gunler else None}
        except Exception as e:
            cikti[pkt] = {"hata": repr(e)[:120]}
        time.sleep(0.5)
    return cikti


def uc_pypi():
    """~362 gunluk pencere -> eski veri dusuyor. SIKI rate-limit: 2 sn bekle."""
    cikti = {}
    for pkt in PYPI_PAKETLER:
        try:
            _, d = cek("https://pypistats.org/api/packages/%s/overall" % pkt)
            veri = d.get("data", [])
            wo = [x for x in veri if x.get("category") == "without_mirrors"]
            cikti[pkt] = {"kayit": len(veri), "aynasiz_gun": len(wo),
                          "ilk_tarih": veri[0].get("date") if veri else None,
                          "son_tarih": veri[-1].get("date") if veri else None,
                          "aynasiz_toplam": sum(x.get("downloads", 0) for x in wo),
                          "aynasiz_son30g": sum(x.get("downloads", 0) for x in wo[-30:])}
        except Exception as e:
            cikti[pkt] = {"hata": repr(e)[:120]}
        time.sleep(2)
    return cikti


def uc_github():
    """Anlik snapshot; tarihsel yildiz serisi bu ucta YOK. 60 istek/saat (kimliksiz)."""
    cikti = {}
    for depo in GH_DEPOLAR:
        try:
            _, d = cek("https://api.github.com/repos/%s" % depo)
            cikti[depo] = {"yildiz": d.get("stargazers_count"), "catal": d.get("forks_count"),
                           "izleyen": d.get("subscribers_count"),
                           "acik_konu": d.get("open_issues_count"),
                           "son_push": d.get("pushed_at")}
        except Exception as e:
            cikti[depo] = {"hata": repr(e)[:120]}
        time.sleep(1)
    return cikti


UCLAR = [
    ("x402_discovery",            uc_x402,                 "kaynak-basi 30g cagri/odeyen; ROLLING PENCERE = arsivlenmiyor"),
    ("sherlock_leaderboard",      uc_sherlock_leaderboard, "arastirmaci omur-boyu kazanc; KUMULATIF = tarih parametresi yok"),
    ("sherlock_contests",         uc_sherlock_contests,    "yarisma metadata; arsivli"),
    ("defillama_fees_ai_agents",  uc_defillama_kategori,   "AI Agents kategori kesiti"),
    ("defillama_summary_virtuals",uc_defillama_protokol,   "yogunlasmanin merkezi; gunluk seri arsivli"),
    ("apify_store",               uc_apify_store,          "aktor-basi kullanici; 7/30/90g KAYAN pencere = dusuyor"),
    ("hf_models",                 uc_hf_modeller,          "kumulatif indirme; resmi TARIHSEL uc YOK"),
    ("npm_downloads",             uc_npm,                  "~547 gune kirpiliyor = eski veri dusuyor"),
    ("pypi_downloads",            uc_pypi,                 "~362 gun pencere = eski veri dusuyor"),
    ("github_repos",              uc_github,               "anlik snapshot; tarihsel yildiz serisi yok"),
]


def main():
    simdi = datetime.now(timezone.utc).isoformat(timespec="seconds")
    satirlar = []
    for ad, fn, notu in UCLAR:
        kayit = {"zaman_utc": simdi, "surum": SURUM, "uc": ad, "not": notu}
        t0 = time.time()
        try:
            kayit["ozet"] = fn()
            kayit["durum"] = "HATA-ICERIDE" if isinstance(kayit["ozet"], dict) and kayit["ozet"].get("hata") else "OK"
        except urllib.error.HTTPError as e:
            kayit["durum"] = "HTTP-HATA"; kayit["http"] = e.code
        except Exception as e:
            kayit["durum"] = "HATA"; kayit["hata"] = repr(e)[:200]
        kayit["saniye"] = round(time.time() - t0, 2)
        satirlar.append(kayit)
        print("  %-28s %-12s %5.1fs" % (ad, kayit["durum"], kayit["saniye"]))

    with open(SERI, "a", encoding="utf-8") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    basarili = sum(1 for s in satirlar if s["durum"] == "OK")
    print("\nyazildi: %s  (%d/%d uc OK)" % (SERI, basarili, len(satirlar)))
    if basarili < len(satirlar):
        print("🔴 EKSIK UC VAR — 'exit=0 + sifir satir' tuzagi icin kural-12f: durumu oku, sayiya guvenme.")
    return 0 if basarili else 1


if __name__ == "__main__":
    sys.exit(main())
