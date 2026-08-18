#!/usr/bin/env python3
"""AI SUPPLY INDEX — collector for the supply side of the AI economy (weekly snapshot).

WHY: public measurement of AI mostly covers DEMAND (how many people use it, for what).
The supply side — who is actually earning, and how concentrated those earnings are — is
measured far less often, and several of these endpoints KEEP NO HISTORY: a snapshot not
taken this week cannot be reconstructed later.

No authentication. Read-only. The only file written is the series next to this script.

DESIGN NOTES
  - v0.1 counted only TOTALS and threw the DISTRIBUTION away. But the finding lives in the
    distribution ("94.1 % below $1", "lifetime median $459"), so percentiles + histogram +
    top-10 are archived for x402, Sherlock, Apify, Hugging Face and DeFiLlama.
  - Every endpoint's response shape was measured live on 2026-08-18 — none of it is guessed.
  - Schema-break brake: when a response no longer has the expected shape the collector does
    NOT silently count 0. It returns None plus an `olculemedi` (unmeasurable) reason string,
    which the freshness watchdog turns red. A silent zero is worse than a visible failure.

DELIBERATELY NOT INCLUDED (stated, not hidden):
  - layoffs.fyi /api/annual-stats : full backend URL not recorded during discovery (unmeasured).
  - Gumroad product page HTML     : fragile scrape, product URL must be known in advance.
  - Replicate model page HTML     : fragile scrape, yields a single cumulative number.
  None of these is "impossible" — each is "not measured in this round". Trigger: if and when
  HTML scraping becomes acceptable.

LANGUAGE: user-facing output (this docstring, printed lines, record annotations) is English.
Internal identifiers and the published JSON keys remain Turkish — the keys are frozen for
series continuity. See the Schema section of README.md for the full key map, and use
`to_english.py` to generate an English-keyed mirror of the series.
"""
import json, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
SERI = KOK / "ai-arz-serisi.ndjson"
UA = "Mozilla/5.0 (compatible; mergen-arz-olcum/0.3)"
ZAMAN_ASIMI = 30
SURUM = "0.3"

# OPEN-WINDOW WATCH: how many open entries are LISTED per record.
# The count is always exact; this cap only bounds record size (the series is append-only).
PENCERE_LISTE_TAVANI = 10

NPM_PAKETLER = ["@anthropic-ai/sdk", "openai", "langchain", "@langchain/core",
                "ai", "@modelcontextprotocol/sdk"]
PYPI_PAKETLER = ["anthropic", "openai", "langchain", "crewai"]
GH_DEPOLAR = ["langchain-ai/langchain", "anthropics/anthropic-sdk-python",
              "crewAIInc/crewAI", "modelcontextprotocol/servers",
              "Significant-Gravitas/AutoGPT"]
LLAMA_PROTOKOL = "virtuals-protocol"   # 89.7 % of the AI-Agents category
X402_SAYFA_TAVANI = 60                 # 60*500 = 30,000 resources; safety brake


# ------------------------------------------------------------------- helpers
def cek(url, ham=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=ZAMAN_ASIMI) as r:
        b = r.read()
        return (r.status, b) if ham else (r.status, json.loads(b))


def yuzdelik(dizi, p):
    """Nearest-rank percentile, no linear interpolation. `dizi` must already be sorted."""
    if not dizi:
        return None
    k = int(round((len(dizi) - 1) * p / 100.0))
    return dizi[max(0, min(k, len(dizi) - 1))]


def dagilim_ozeti(degerler, kovalar):
    """Compact archivable summary of a list of numbers: n, total, percentiles, histogram."""
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
    # concentration: share of the largest single value and of the largest ten
    if o["toplam"] > 0:
        o["top1_pay"] = round(d[-1] / o["toplam"], 4)
        o["top10_pay"] = round(sum(d[-10:]) / o["toplam"], 4)
    return o


# ---------------------------------------------------------------- collectors
def uc_x402():
    """Walk every page, archive the per-resource 30-day call/payer DISTRIBUTION.
    Shape: {items:[{resource,quality:{l30DaysTotalCalls,l30DaysUniquePayers}}], pagination:{total}}
    ROLLING 30-DAY WINDOW: there is no history — what is not captured today is gone."""
    tab = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=500&offset=%d"
    cagri, odeyen, toplam, sayfa = [], [], None, 0
    ilk_uc = []
    while sayfa < X402_SAYFA_TAVANI:
        _, d = cek(tab % (sayfa * 500))
        ogeler = d.get("items", [])
        if toplam is None:
            toplam = d.get("pagination", {}).get("total")
        for it in ogeler:
            # MEASURED 2026-08-18: these fields are NOT top level, they sit under it["quality"].
            # The first v0.2 draft looked at top level -> walked 151 pages and collected 0 values
            # (the "exit=0 + zero rows" trap). Caught in a dry run; never reached the data.
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
    """Shape: {handle: {payout, score, ranking, ...}} — CUMULATIVE, no date parameter.
    v0.1 only counted entries; the real finding is in the LIFETIME EARNINGS DISTRIBUTION."""
    _, d = cek("https://mainnet-contest.sherlock.xyz/stats/leaderboard")
    if not isinstance(d, dict):
        return {"hata": "expected a dict, got: %s" % type(d).__name__}
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


def _iso_epoch(s):
    """ISO-8601 -> epoch seconds. Returns None if unparseable (never silently 0)."""
    if not isinstance(s, str) or not s:
        return None
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


def _kapi(kaynak, kimlik, baslik, biter_ep, kamu, odul=None, url=None, etiket=None):
    return {"arena": kaynak, "id": kimlik, "baslik": str(baslik)[:120], "kamu": bool(kamu),
            "biter_utc": datetime.fromtimestamp(biter_ep, timezone.utc).isoformat(timespec="seconds"),
            "kalan_gun": round((biter_ep - time.time()) / 86400.0, 2),
            "odul": odul, "url": url, "etiket": etiket}


def uc_sherlock_contests():
    """Arena 1 of the OPEN-WINDOW WATCH.

    v0.2 counted only `total` and discarded the status/starts_at/ends_at the API returns.
    v0.3: SAME endpoint, but entries with `ends_at > now` are counted AND listed — because
    "301 contests exist" and "0 are open right now" are very different facts.

    COVERAGE [measured 2026-08-18]: the default page holds 10 items => 31 requests.
    `per_page=100` WAS TESTED LIVE AND WORKS (?limit / ?page_size do NOT: both returned 10)
    => 4 requests / 301 records. Every page is walked; ranking is never trusted.

    SCHEMA-BREAK BRAKE (the `contests` vs `items` trap bit us the same day): if `items` is
    missing, OR no item carries a numeric `ends_at`, do NOT silently count 0 — return
    acik_yarisma=None plus an `olculemedi` reason. The watchdog turns that red.
    """
    simdi = int(time.time())
    ogeler, toplam, sayfa, sayfa_alani = [], None, 0, None
    while sayfa < 40:
        _, d = cek("https://mainnet-contest.sherlock.xyz/contests?per_page=100&page=%d" % (sayfa + 1))
        if not isinstance(d, dict) or "items" not in d:
            return {"yarisma_sayisi": None, "sayfa_ogesi": 0, "sayfa": sayfa,
                    "acik_yarisma": None, "acik_kamu": None, "acik_kapilar": [],
                    "olculemedi": "schema broken: response has no `items` (type=%s)" % type(d).__name__}
        its = d.get("items") or []
        if toplam is None:
            toplam, sayfa_alani = d.get("total"), d.get("pages")
        ogeler.extend(its)
        sayfa += 1
        if not d.get("has_next"):
            break
        time.sleep(0.2)

    ends_dolu = sum(1 for i in ogeler if isinstance(i.get("ends_at"), (int, float)))
    if ogeler and ends_dolu == 0:
        return {"yarisma_sayisi": toplam, "sayfa_ogesi": len(ogeler), "sayfa": sayfa,
                "acik_yarisma": None, "acik_kamu": None, "acik_kapilar": [],
                "olculemedi": "schema broken: none of the %d items has a numeric `ends_at`" % len(ogeler)}

    acik, kamu = [], []
    for i in ogeler:
        e = i.get("ends_at")
        if not (isinstance(e, (int, float)) and e > simdi):
            continue
        tl = str(i.get("type_label") or "")
        k = (not i.get("private")) and tl.startswith("Public") and ("Bug Bounty" not in tl)
        kapi = _kapi("sherlock", i.get("id"), i.get("title"), int(e), k,
                     odul=i.get("prize_pool"), etiket=tl,
                     url="https://audits.sherlock.xyz/contests/%s" % i.get("id"))
        acik.append(kapi)
        if k:
            kamu.append(kapi)
    acik.sort(key=lambda x: x["kalan_gun"])
    return {"yarisma_sayisi": toplam, "sayfa_ogesi": len(ogeler), "sayfa": sayfa,
            "sayfa_alani": sayfa_alani,
            "acik_yarisma": len(acik), "acik_kamu": len(kamu),
            "acik_kapilar": acik[:PENCERE_LISTE_TAVANI]}


def uc_code4rena_audits():
    """Arena 2 of the watch. ENDPOINT MEASURED 2026-08-18 (no auth, 200 JSON):
      https://code4rena.com/api/v1/audits  ->  {data:{audits:[...]}, pagination:{total,lastPage,perPage}}
    perPage is FIXED at 25: ?limit= / ?pageSize= / ?perPage= all returned HTTP 400 => 19 pages / 475 records.
    Fields: startTime/endTime ISO-8601 · status (Completed/Reporting/...) · codeAccess (public|top_secret).
    A PUBLIC OPEN ENTRY = codeAccess=='public' AND endTime>now. Ordering was measured as startTime-desc
    but no verdict depends on ordering — all 19 pages are walked."""
    simdi = int(time.time())
    ogeler, toplam, sayfa, son_sayfa = [], None, 0, None
    while sayfa < 40:
        _, d = cek("https://code4rena.com/api/v1/audits?page=%d" % (sayfa + 1))
        au = ((d or {}).get("data") or {}).get("audits") if isinstance(d, dict) else None
        if not isinstance(au, list):
            return {"yarisma_sayisi": None, "sayfa_ogesi": 0, "sayfa": sayfa,
                    "acik_yarisma": None, "acik_kamu": None, "acik_kapilar": [],
                    "olculemedi": "schema broken: no data.audits list (type=%s)" % type(d).__name__}
        pg = d.get("pagination") or {}
        if toplam is None:
            toplam, son_sayfa = pg.get("total"), pg.get("lastPage")
        ogeler.extend(au)
        sayfa += 1
        if not pg.get("nextPage"):
            break
        time.sleep(0.2)

    end_dolu = sum(1 for a in ogeler if _iso_epoch(a.get("endTime")) is not None)
    if ogeler and end_dolu == 0:
        return {"yarisma_sayisi": toplam, "sayfa_ogesi": len(ogeler), "sayfa": sayfa,
                "acik_yarisma": None, "acik_kamu": None, "acik_kapilar": [],
                "olculemedi": "schema broken: none of the %d items has a parseable `endTime`" % len(ogeler)}

    acik, kamu = [], []
    for a in ogeler:
        e = _iso_epoch(a.get("endTime"))
        if e is None or e <= simdi:
            continue
        k = (a.get("codeAccess") == "public")
        kapi = _kapi("code4rena", a.get("slug") or a.get("uid"), a.get("title"), e, k,
                     odul=a.get("formattedAmount"), etiket=a.get("auditType"),
                     url="https://code4rena.com/audits/%s" % (a.get("slug") or ""))
        acik.append(kapi)
        if k:
            kamu.append(kapi)
    acik.sort(key=lambda x: x["kalan_gun"])
    return {"yarisma_sayisi": toplam, "sayfa_ogesi": len(ogeler), "sayfa": sayfa,
            "son_sayfa_alani": son_sayfa,
            "acik_yarisma": len(acik), "acik_kamu": len(kamu),
            "acik_kapilar": acik[:PENCERE_LISTE_TAVANI]}


def uc_cantina_competitions():
    """Arena 3 of the watch. ENDPOINT MEASURED 2026-08-18 (no auth, 200 JSON, ONE request, n=144):
      https://cantina.xyz/api/v0/competitions  ->  FLAT LIST
    Fields: timeframe.{start,end} ISO · status (live|complete|escalations_ended) · kind
    (public_contest 125 | private_contest 19) · kycRequired · totalRewardPot.
    MEASURED: the `joined` field reads 'restricted' in 144/144 records => it is NOT a privacy
    signal (it only says we have not joined). Public/private is decided by `kind` alone.

    NOTE: this collector is implemented and measured but NOT yet wired into UCLAR below."""
    simdi = int(time.time())
    _, d = cek("https://cantina.xyz/api/v0/competitions")
    if not isinstance(d, list):
        return {"yarisma_sayisi": None, "sayfa_ogesi": 0, "sayfa": 1,
                "acik_yarisma": None, "acik_kamu": None, "acik_kapilar": [],
                "olculemedi": "schema broken: expected a list, got type=%s" % type(d).__name__}
    end_dolu = sum(1 for x in d if isinstance(x, dict) and _iso_epoch((x.get("timeframe") or {}).get("end")))
    if d and end_dolu == 0:
        return {"yarisma_sayisi": len(d), "sayfa_ogesi": len(d), "sayfa": 1,
                "acik_yarisma": None, "acik_kamu": None, "acik_kapilar": [],
                "olculemedi": "schema broken: none of the %d items has a parseable timeframe.end" % len(d)}
    acik, kamu = [], []
    for x in d:
        if not isinstance(x, dict):
            continue
        e = _iso_epoch((x.get("timeframe") or {}).get("end"))
        if e is None or e <= simdi:
            continue
        k = (x.get("kind") == "public_contest")
        kapi = _kapi("cantina", x.get("id"), x.get("name"), e, k,
                     odul=x.get("totalRewardPot"), etiket=x.get("kind"), url=x.get("url"))
        kapi["kyc"] = x.get("kycRequired")
        acik.append(kapi)
        if k:
            kamu.append(kapi)
    acik.sort(key=lambda x: x["kalan_gun"])
    return {"yarisma_sayisi": len(d), "sayfa_ogesi": len(d), "sayfa": 1,
            "acik_yarisma": len(acik), "acik_kamu": len(kamu),
            "acik_kapilar": acik[:PENCERE_LISTE_TAVANI]}


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
    """Daily revenue series for a single protocol (~671 days archived). The centre of concentration."""
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
    """Shape: {data:{total,count,items:[{name,username,stats:{totalUsers,...}}]}}
    An earlier finding was "median 2 users" — this endpoint keeps that finding under live watch."""
    tab = "https://api.apify.com/v2/store?limit=100&offset=%d&sortBy=popularity"
    kullanici, toplam, sayfa, en_iyi = [], None, 0, []
    while sayfa < 10:                      # 1,000 actors: the popularity-ranked upper tier
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
            "kapsam_notu": "top 1000 by popularity (upper tier) — NOT the store median",
            "toplam_kullanici_dagilimi": dagilim_ozeti(kullanici, [1, 10, 100, 1000, 10000]),
            "top10": [{"aktor": a, "kullanici": k} for k, a in en_iyi[:10]]}


def uc_hf_modeller():
    """Cumulative downloads — there is no official HISTORICAL endpoint. We are the archive."""
    _, d = cek("https://huggingface.co/api/models?sort=downloads&direction=-1&limit=100")
    if not isinstance(d, list):
        return {"hata": "expected a list"}
    ind = [x.get("downloads") for x in d if isinstance(x.get("downloads"), (int, float))]
    return {"model_sayisi": len(d),
            "indirme_dagilimi": dagilim_ozeti(ind, [1000, 100000, 1000000, 10000000]),
            "top10": [{"id": x.get("id"), "indirme": x.get("downloads"), "begeni": x.get("likes")}
                      for x in d[:10]]}


def uc_npm():
    """The server clips the requested range to ~547 days -> OLD DATA FALLS OFF. Archive it."""
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
    """~362-day window -> old data falls off. STRICT rate limit: wait 2 s between packages."""
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
    """Point-in-time snapshot; this endpoint has no historical star series. 60 req/h unauthenticated."""
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
    ("x402_discovery",            uc_x402,                 "per-resource 30d calls/payers; ROLLING WINDOW = not archived upstream"),
    ("sherlock_leaderboard",      uc_sherlock_leaderboard, "researcher lifetime earnings; CUMULATIVE = no date parameter"),
    ("sherlock_contests",         uc_sherlock_contests,    "contest metadata + OPEN-WINDOW watch; archived"),
    # Arena 2 of the open-window watch: open entries are not a Sherlock-only phenomenon.
    ("code4rena_audits",          uc_code4rena_audits,     "audit metadata + OPEN-WINDOW watch; all 19 pages walked"),
    ("defillama_fees_ai_agents",  uc_defillama_kategori,   "AI Agents category cross-section"),
    ("defillama_summary_virtuals",uc_defillama_protokol,   "the centre of concentration; daily series archived"),
    ("apify_store",               uc_apify_store,          "users per actor; 7/30/90d SLIDING window = data falls off"),
    ("hf_models",                 uc_hf_modeller,          "cumulative downloads; no official HISTORICAL endpoint"),
    ("npm_downloads",             uc_npm,                  "clipped to ~547 days = old data falls off"),
    ("pypi_downloads",            uc_pypi,                 "~362-day window = old data falls off"),
    ("github_repos",              uc_github,               "point-in-time snapshot; no historical star series"),
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
    print("\nwritten: %s  (%d/%d endpoints OK)" % (SERI, basarili, len(satirlar)))
    if basarili < len(satirlar):
        print("ENDPOINT MISSING — read the `durum` field, do not trust the row count "
              "('exit=0 with zero content' is the trap this guards against).")
    return 0 if basarili else 1


if __name__ == "__main__":
    sys.exit(main())
