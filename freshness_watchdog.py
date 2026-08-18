#!/usr/bin/env python3
"""freshness_watchdog.py — the CONSUMER of the AI Supply Index collector.

WHY IT EXISTS (the collector's own warning): "response shapes were measured live on
2026-08-18; if an endpoint's schema changes the collector may silently return 0/None".
That is the classic "exit=0 with zero content" trap: cron is green, the file grows, but
the load-bearing number is 0 — a fake green. A collector that silently returns zero is
worse than one that visibly fails.

FOUR INDEPENDENT FAULT CLASSES ARE MEASURED (none of them can see the others):
  (1) STALENESS  — age of the last RECORD stamp (NOT the file mtime: a touched-but-unwritten
                   file produces a fake green; both are reported, the verdict uses the RECORD)
  (2) ZERO/NONE  — is any endpoint's load-bearing number 0/None/missing in the last run
                   (= the schema broke)
  (3) FROZEN     — how many consecutive runs returned the identical value (endpoint alive
                   but repeating itself)
  (+) MISSING    — does the last run carry fewer endpoints than expected (one dropped silently)

EXIT CODE: 0=GREEN · 1=YELLOW · 2=RED   (usable directly in cron / `||` chains)

SELF-TEST: `--self-test` makes the watchdog BITE ITSELF first (fake-stale, fake-zero,
fake-frozen and missing-endpoint must go RED/YELLOW; a healthy series must stay GREEN).
If it does not bite, the detector is wrong.

LANGUAGE: user-facing output (this docstring, CLI help, printed lines, findings) is English.
Internal identifiers and the published JSON keys remain Turkish — the series keys are frozen
for continuity. See the Schema section of README.md, and `to_english.py` for an English mirror.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
VARSAYILAN_SERI = KOK / "ai-arz-serisi.ndjson"

# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLD DERIVATION — every threshold comes from a MEASUREMENT, none is a guess.
# (This mechanism fixes the MEASUREMENT, never the VERDICT: red means "a human should
# look", not an automatic decision.)
#
# MEASURED [2026-08-18, ai-arz-serisi.ndjson]:
#   - the series carried 14 records / 2 runs; both runs on 2026-08-18 (07:04:52Z, 07:51:45Z)
#   - the v0.1 run had 4 endpoints, the v0.2 run had 10 => KAYITLI_UC = 10 (last run's count)
#   - planned cadence = WEEKLY cron ("0 7 * * 1")
#
# STALENESS thresholds derive from that cadence:
#   cadence 7 days + 1 day of run-window/host-delay slack => YELLOW at 8 days
#     ("a run slipped, intervene")
#   2 x cadence                                           => RED at 14 days
#     ("a run was DEFINITELY missed"; on the x402 rolling-30d and Apify sliding-window
#      endpoints a missed week CANNOT BE REGENERATED)
TAZELIK_SARI_GUN = 8
TAZELIK_KIRMIZI_GUN = 14

# FROZEN threshold: with n=2 runs a STATISTICAL calibration is IMPOSSIBLE [stated].
# Starting value is 3 consecutive-identical (~3 weeks) and deliberately YELLOW (not RED):
# slow-moving counters (sherlock_contests=301, ai_agent_protokol_sayisi=17) can legitimately
# stay flat FOR WEEKS => an automatic RED would manufacture a fake red.
# RE-DERIVATION DEBT: once 6 runs (~6 weeks) have accumulated, re-measure this from the series.
DONMUS_ESIK = 3
DONMUS_YENIDEN_TURET_KOSU = 6

# FROZEN also carries a TIME-SPREAD condition. ROOT CAUSE [found by live measurement
# 2026-08-18T15:05Z]: on the first VPS run the series held 3 runs on the SAME DAY (07:04,
# 07:51, 15:04), so slow counters (sherlock=1710, contests=301, protocol=17) were naturally
# identical and the watchdog went yellow. That was a FAKE RED: counting "3 runs" is
# cadence-independent. Frozen-ness only means something once REAL TIME has passed. Three
# weekly runs span ~14 days; with drift slack the minimum spread is 10 days => same-day and
# consecutive-day repeats NEVER raise an alarm.
DONMUS_MIN_YAYILIM_GUN = 10

KAYITLI_UC = 10

# LOAD-BEARING NUMBER — the single value that decides whether an endpoint's row is full or empty.
# All were MEASURED from the 2026-08-18 run; none of them was 0 (the smallest was 17), so a
# 0/None here means the schema broke (there is no legitimate-zero scenario).
def _topla(ozet, alan):
    """Sum `alan` across nested dicts (npm/pypi/github carry a per-package sub-dict)."""
    if not isinstance(ozet, dict):
        return None
    t, bulundu = 0, False
    for v in ozet.values():
        if isinstance(v, dict) and isinstance(v.get(alan), (int, float)):
            t += v[alan]
            bulundu = True
    return t if bulundu else None


def _duz(ozet, alan):
    return ozet.get(alan) if isinstance(ozet, dict) else None


TASIYICILAR = {
    "x402_discovery":             lambda o: _duz(o, "kaynak_sayisi"),
    "sherlock_leaderboard":       lambda o: _duz(o, "arastirmaci_sayisi"),
    "sherlock_contests":          lambda o: _duz(o, "yarisma_sayisi"),
    "defillama_fees_ai_agents":   lambda o: _duz(o, "ai_agent_protokol_sayisi"),
    "defillama_summary_virtuals": lambda o: _duz(o, "total30d"),
    "apify_store":                lambda o: _duz(o, "magaza_toplam_aktor"),
    "hf_models":                  lambda o: _duz(o, "model_sayisi"),
    "npm_downloads":              lambda o: _topla(o, "toplam_30g"),
    "pypi_downloads":             lambda o: _topla(o, "aynasiz_toplam"),
    "github_repos":               lambda o: _topla(o, "yildiz"),
}


def kayitlar(seri: Path):
    out = []
    if not seri.exists():
        return out
    for satir in seri.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir:
            continue
        try:
            out.append(json.loads(satir))
        except json.JSONDecodeError:
            pass
    return out


def _yas_gun(ts: str, simdi: datetime):
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (simdi - d).total_seconds() / 86400.0
    except Exception:
        return None


def denetle(seri: Path, simdi=None):
    """Measure all legs. Returns (code, report_dict). Code: 0 green / 1 yellow / 2 red."""
    simdi = simdi or datetime.now(timezone.utc)
    r = {"series": str(seri), "measured_utc": simdi.isoformat(timespec="seconds"),
         "findings": [], "severity": "GREEN"}
    kirmizi, sari = [], []

    rows = kayitlar(seri)
    r["record_count"] = len(rows)
    if not rows:
        r["findings"].append("RED series is EMPTY or MISSING: %s" % seri)
        r["severity"] = "RED"
        return 2, r

    # ── (1) STALENESS ───────────────────────────────────────────────────────
    damgalar = sorted({x.get("zaman_utc", "") for x in rows if x.get("zaman_utc")})
    son_damga = damgalar[-1] if damgalar else None
    r["last_record_utc"] = son_damga
    r["run_count"] = len(damgalar)
    yas = _yas_gun(son_damga, simdi) if son_damga else None
    r["record_age_days"] = round(yas, 3) if yas is not None else None
    # file mtime is reported SEPARATELY (to separate touched-but-not-written); verdict uses the RECORD
    try:
        r["file_mtime_age_days"] = round(
            (simdi - datetime.fromtimestamp(seri.stat().st_mtime, timezone.utc)).total_seconds() / 86400.0, 3)
    except Exception:
        r["file_mtime_age_days"] = None

    if yas is None:
        kirmizi.append("last record stamp UNREADABLE (zaman_utc missing/corrupt)")
    elif yas > TAZELIK_KIRMIZI_GUN:
        kirmizi.append("STALE: last record %.1f days ago (red threshold %d d = 2 cadences; "
                       "a missed week CANNOT BE REGENERATED on rolling endpoints)" % (yas, TAZELIK_KIRMIZI_GUN))
    elif yas > TAZELIK_SARI_GUN:
        sari.append("delay: last record %.1f days ago (yellow threshold %d d = cadence + slack)"
                    % (yas, TAZELIK_SARI_GUN))

    # ── records belonging to the last run ───────────────────────────────────
    son_kosu = [x for x in rows if x.get("zaman_utc") == son_damga]
    r["last_run_endpoint_count"] = len(son_kosu)

    # ── (+) MISSING ENDPOINT ────────────────────────────────────────────────
    if len(son_kosu) < KAYITLI_UC:
        eksikler = sorted(set(TASIYICILAR) - {x.get("uc") for x in son_kosu})
        kirmizi.append("MISSING-ENDPOINT: last run has %d/%d endpoints; dropped=%s"
                       % (len(son_kosu), KAYITLI_UC, ",".join(eksikler) or "?"))

    # ── (2) ZERO/NONE + status ──────────────────────────────────────────────
    tasiyici_son = {}
    for k in son_kosu:
        uc = k.get("uc", "?")
        durum = k.get("durum")
        if durum and durum != "OK":
            kirmizi.append("ENDPOINT-ERROR: %s status=%s" % (uc, durum))
        cikar = TASIYICILAR.get(uc)
        if cikar is None:
            continue
        deger = cikar(k.get("ozet"))
        tasiyici_son[uc] = deger
        if deger is None:
            kirmizi.append("SILENT-NONE: %s has no load-bearing number (schema broke)" % uc)
        elif deger == 0:
            kirmizi.append("SILENT-ZERO: %s load-bearing number is 0 (schema broke; "
                           "in the 2026-08-18 measurement the smallest was 17)" % uc)
    r["last_run_carriers"] = tasiyici_son

    # ── (3) FROZEN SERIES ───────────────────────────────────────────────────
    donmus = {}
    for uc, cikar in TASIYICILAR.items():
        dizi, dizi_ts = [], []
        for d in damgalar[::-1]:                      # newest to oldest
            for k in rows:
                if k.get("zaman_utc") == d and k.get("uc") == uc:
                    dizi.append(cikar(k.get("ozet")))
                    dizi_ts.append(d)
                    break
        n = 1
        for i in range(1, len(dizi)):
            if dizi[i] is not None and dizi[i] == dizi[0]:
                n += 1
            else:
                break
        if len(dizi) >= 2:
            donmus[uc] = n
        # TIME-SPREAD condition: same-day repeats are NOT frozen-ness (fake-red brake)
        yayilim = 0.0
        if n >= 2:
            y = _yas_gun(dizi_ts[n - 1], simdi)
            e = _yas_gun(dizi_ts[0], simdi)
            if y is not None and e is not None:
                yayilim = y - e
        if n >= DONMUS_ESIK and yayilim >= DONMUS_MIN_YAYILIM_GUN:
            sari.append("FROZEN: %s returned the same value (%s) for the last %d runs, spread over "
                        "%.1f days; thresholds=%d runs & %d days [n=2 calibration debt outstanding]"
                        % (uc, dizi[0], n, yayilim, DONMUS_ESIK, DONMUS_MIN_YAYILIM_GUN))
    r["consecutive_identical"] = donmus

    r["findings"] = ["RED " + x for x in kirmizi] + ["YELLOW " + x for x in sari]
    if kirmizi:
        r["severity"] = "RED"
        return 2, r
    if sari:
        r["severity"] = "YELLOW"
        return 1, r
    r["findings"].append("GREEN fresh(%.2fd) · %d/%d endpoints populated · no frozen series"
                         % (yas or 0, len(tasiyici_son), KAYITLI_UC))
    return 0, r


def deftere_yaz(defter: Path, r: dict, kod: int):
    if kod == 0:
        return
    kayit = {"ts": r["measured_utc"], "source": "ai-arz-tazelik",
             "sev": "CRITICAL" if kod == 2 else "WARN",
             "dedup_key": "ai-arz|tazelik|%s" % r["severity"],
             "konu": "ai-arz-toplayici", "sinif": "AI_ARZ_%s" % r["severity"],
             "msg": " | ".join(r["findings"])[:600],
             "meta": {"record_age_days": r.get("record_age_days"),
                      "last_run_endpoint_count": r.get("last_run_endpoint_count"),
                      "carriers": r.get("last_run_carriers")}}
    defter.parent.mkdir(parents=True, exist_ok=True)
    with open(defter, "a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# SELF-TEST — the watchdog BITES ITSELF first
# ═════════════════════════════════════════════════════════════════════════════
def _satir(ts, uc, ozet, durum="OK"):
    return json.dumps({"zaman_utc": ts, "surum": "0.2", "uc": uc,
                       "ozet": ozet, "durum": durum}, ensure_ascii=False)


_SAGLAM = {
    "x402_discovery": {"kaynak_sayisi": 15095}, "sherlock_leaderboard": {"arastirmaci_sayisi": 1710},
    "sherlock_contests": {"yarisma_sayisi": 301}, "defillama_fees_ai_agents": {"ai_agent_protokol_sayisi": 17},
    "defillama_summary_virtuals": {"total30d": 1055670}, "apify_store": {"magaza_toplam_aktor": 47744},
    "hf_models": {"model_sayisi": 100}, "npm_downloads": {"pkg": {"toplam_30g": 115914002}},
    "pypi_downloads": {"anthropic": {"aynasiz_toplam": 802816271}},
    "github_repos": {"lc/lc": {"yildiz": 144448}},
}


def _seri_yaz(yol, kosular):
    """Write a synthetic series. Each run is (timestamp, {endpoint: summary}, status_override)."""
    with open(yol, "w", encoding="utf-8") as f:
        for ts, ucler, durumlar in kosular:
            for uc, ozet in ucler.items():
                f.write(_satir(ts, uc, ozet, durumlar.get(uc, "OK")) + "\n")


def _kaydir(ozetler, artis):
    """Simulate growing counters (so the frozen alarm is not triggered)."""
    import copy
    y = copy.deepcopy(ozetler)
    for uc, o in y.items():
        for k, v in list(o.items()):
            if isinstance(v, (int, float)):
                o[k] = v + artis
            elif isinstance(v, dict):
                for k2, v2 in list(v.items()):
                    if isinstance(v2, (int, float)):
                        v[k2] = v2 + artis
    return y


def oz_test():
    simdi = datetime(2026, 8, 18, 15, 0, tzinfo=timezone.utc)
    tmp = Path(tempfile.mkdtemp(prefix="ai-supply-selftest-"))
    gecti, kaldi = 0, 0

    def kos(ad, kosular, beklenen, simdi_=simdi):
        nonlocal gecti, kaldi
        yol = tmp / (ad + ".ndjson")
        _seri_yaz(yol, kosular)
        kod, r = denetle(yol, simdi_)
        ad_bek = {0: "GREEN", 1: "YELLOW", 2: "RED"}
        ok = kod == beklenen
        gecti += ok
        kaldi += (not ok)
        print("  [%s] %-22s expected=%-7s measured=%-7s" % ("PASS" if ok else "FAIL",
              ad, ad_bek[beklenen], ad_bek[kod]))
        for b in r["findings"][:2]:
            print("          %s" % b[:118])
        return ok

    def gun_once(n):
        return (simdi - timedelta(days=n)).isoformat(timespec="seconds")

    print("SELF-TEST — the watchdog bites ITSELF first")
    print("  thresholds: STALE yellow=%dd red=%dd · FROZEN=%d runs · EXPECTED ENDPOINTS=%d"
          % (TAZELIK_SARI_GUN, TAZELIK_KIRMIZI_GUN, DONMUS_ESIK, KAYITLI_UC))
    print()

    # 1) HEALTHY: fresh + populated + changing => GREEN
    kos("healthy", [(gun_once(14), _kaydir(_SAGLAM, -20), {}),
                    (gun_once(7), _kaydir(_SAGLAM, -10), {}),
                    (gun_once(1), _SAGLAM, {})], 0)

    # 2) FAKE-FRESH: content is fine but 30 days old => RED
    kos("fake-stale", [(gun_once(44), _kaydir(_SAGLAM, -20), {}),
                       (gun_once(37), _kaydir(_SAGLAM, -10), {}),
                       (gun_once(30), _SAGLAM, {})], 2)

    # 3) BORDERLINE DELAY: 9 days (yellow band) => YELLOW
    kos("borderline-delay", [(gun_once(23), _kaydir(_SAGLAM, -20), {}),
                             (gun_once(16), _kaydir(_SAGLAM, -10), {}),
                             (gun_once(9), _SAGLAM, {})], 1)

    # 4) FAKE-ZERO: fresh but one endpoint returns 0 (schema broke) => RED
    bozuk = dict(_SAGLAM); bozuk["sherlock_leaderboard"] = {"arastirmaci_sayisi": 0}
    kos("fake-zero", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                      (gun_once(1), bozuk, {})], 2)

    # 5) FAKE-NONE: field renamed upstream (silent None) => RED
    bozuk2 = dict(_SAGLAM); bozuk2["x402_discovery"] = {"resource_count": 15095}
    kos("fake-none", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                      (gun_once(1), bozuk2, {})], 2)

    # 6) FROZEN: fresh + populated but 3 runs identical, SPREAD over 14 days => YELLOW
    kos("frozen-series", [(gun_once(15), _SAGLAM, {}),
                          (gun_once(8), _SAGLAM, {}),
                          (gun_once(1), _SAGLAM, {})], 1)

    # 6b) FAKE-RED BRAKE [live case 2026-08-18T15:05Z]: 3 runs the SAME DAY, slow counters
    #     naturally identical => NOT frozen => must stay GREEN.
    ayni_gun = [((simdi - timedelta(hours=8)).isoformat(timespec="seconds"), _SAGLAM, {}),
                ((simdi - timedelta(hours=7)).isoformat(timespec="seconds"), _SAGLAM, {}),
                ((simdi - timedelta(hours=1)).isoformat(timespec="seconds"), _SAGLAM, {})]
    kos("same-day-3-runs", ayni_gun, 0)

    # 7) MISSING ENDPOINT: last run has 8 instead of 10 => RED
    eksik = {k: v for k, v in list(_SAGLAM.items())[:8]}
    kos("missing-endpoint", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                             (gun_once(1), eksik, {})], 2)

    # 8) ENDPOINT ERROR: status != OK => RED
    kos("endpoint-error", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                           (gun_once(1), _SAGLAM, {"apify_store": "HTTP-HATA"})], 2)

    # 9) EMPTY SERIES => RED
    bos = tmp / "empty.ndjson"; bos.write_text("", encoding="utf-8")
    kod, _ = denetle(bos, simdi)
    ok = kod == 2
    gecti += ok; kaldi += (not ok)
    print("  [%s] %-22s expected=RED     measured=%s" % ("PASS" if ok else "FAIL",
          "empty-series", {0: "GREEN", 1: "YELLOW", 2: "RED"}[kod]))

    print()
    print("SELF-TEST RESULT: %d passed / %d failed" % (gecti, kaldi))
    return 0 if kaldi == 0 else 1


def main():
    ap = argparse.ArgumentParser(
        description="Freshness / emptiness watchdog for the AI Supply Index collector. "
                    "Exit code: 0=GREEN 1=YELLOW 2=RED.")
    ap.add_argument("--series", default=str(VARSAYILAN_SERI),
                    help="path to the NDJSON series to audit (default: alongside this script)")
    ap.add_argument("--ledger", default="",
                    help="append alarms to this NDJSON ledger (empty = do not write)")
    ap.add_argument("--json", action="store_true",
                    help="print the full report as JSON instead of text")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="make the watchdog bite itself first (fake-stale/zero/frozen must trip it)")
    a = ap.parse_args()

    if a.self_test:
        return oz_test()

    kod, r = denetle(Path(a.series))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print("AI SUPPLY INDEX — FRESHNESS WATCHDOG — %s" % r["severity"])
        print("  series=%s records=%s runs=%s" % (r["series"], r.get("record_count"), r.get("run_count")))
        print("  last record=%s (age %.2f days) · file-mtime age=%s days"
              % (r.get("last_record_utc"), r.get("record_age_days") or -1, r.get("file_mtime_age_days")))
        for b in r["findings"]:
            print("  - %s" % b)
    if a.ledger:
        deftere_yaz(Path(a.ledger), r, kod)
    return kod


if __name__ == "__main__":
    sys.exit(main())
