#!/usr/bin/env python3
"""ai_arz_tazelik_bekci.py — AI-arz toplayicisinin TUKETICISI (s189 T1-icra, 2026-08-18).

NEDEN VAR (T2'nin kendi uyarisi, BENIOKU.md "Bilinen sinirlar" §1):
    "ozet() sekilleri 2026-08-18'de canli olculdu; uc semasi degisirse SESSIZCE 0/None doner"
Yani bu toplayici klasik "exit=0 + sifir icerik" tuzagina acik (kural-12f / s177-EK-f:
uretici-cikti tazeligi). Cron yesil, dosya buyuyor, ama tasiyici sayi 0 =  fake-green.

UC AYRI ARIZA SINIFI OLCULUR (ucu de birbirini GORMEZ — metaculus_tazelik_bekci.py dersi:
"tazelik bekcisi 'dosya TAZE mi' sorar; null-bekcisi 'dosya DOLU mu' sorar"):
  (1) TAZELIK   — son KAYIT damgasinin yasi (dosya mtime'i DEGIL: dokunulmus-ama-yazilmamis
                  dosya fake-green uretir; ikisi de raporlanir, hukum KAYIT damgasindan)
  (2) SIFIR/NONE— son kosuda her ucun TASIYICI sayisi 0/None/eksik mi (= sema kirildi)
  (3) DONMUS    — ardisik ayni deger sayisi (uc yasiyor ama ayni cevabi tekrarliyor)
  (+) EKSIK-UC  — son kosudaki uc sayisi kayittan az mi (bir uc sessizce dustu)

CIKIS KODU: 0=YESIL · 1=SARI · 2=KIRMIZI   (cron/`||` zincirlerinde dogrudan kullanilir)

KURAL-4: `--oz-test` ile once KENDINI isirir (sahte-bayat + sahte-0 + sahte-donmus +
eksik-uc KIRMIZI/SARI vermeli; saglikli seri YESIL). Isirmiyorsa desen yanlistir.
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
# ESIK TURETIMI — hepsi OLCUMDEN gelir, hicbiri sezgisel degil (D-5: bu mekanik
# OLCUMU sabitler, HUKMU degil — kirmizi = "insan baksin", otomatik karar yok).
#
# OLCUM [recomputed 2026-08-18, ai-arz-serisi.ndjson]:
#   - seri 14 kayit / 2 kosu tasiyor; iki kosu da 2026-08-18 (07:04:52Z ve 07:51:45Z)
#   - v0.1 kosusu 4 uc, v0.2 kosusu 10 uc  => KAYITLI_UC = 10 (son kosunun uc sayisi)
#   - planlanan kadans = HAFTALIK cron (s189 §C; "0 7 * * 1")
#
# TAZELIK esikleri kadanstan turetildi:
#   kadans 7 gun + 1 gun kosu-penceresi/host-gecikme payi => SARI 8 gun
#     ("bir kosu gecikti, mudahale et")
#   2 x kadans                                            => KIRMIZI 14 gun
#     ("bir kosu KESIN kacti"; x402 rolling-30g ve apify kayan-pencere uclarinda
#      kacan hafta GERI URETILEMEZ — BENIOKU.md aciliyet gerekcesi)
TAZELIK_SARI_GUN = 8
TAZELIK_KIRMIZI_GUN = 14

# DONMUS esigi: n=2 kosuyla ISTATISTIKSEL kalibrasyon YAPILAMAZ [beyan].
# Baslangic degeri 3 ardisik-ayni (= ~3 hafta) ve bilerek SARI (KIRMIZI degil):
# yavas-hareketli sayaclar (sherlock_contests=301, ai_agent_protokol_sayisi=17)
# HAFTALARCA mesru olarak sabit kalabilir => otomatik KIRMIZI fake-red uretirdi (kural-5).
# YENIDEN-TURETME BORCU: 6 kosu (~6 hafta) birikince esik seriden yeniden olculecek.
DONMUS_ESIK = 3
DONMUS_YENIDEN_TURET_KOSU = 6

# DONMUS ayrica ZAMAN-YAYILIMI sarti tasir. KOK [canli-olcumle bulundu 2026-08-18T15:05Z]:
# ilk VPS kosusunda seri AYNI GUN 3 kosu tasiyordu (07:04, 07:51, 15:04) => yavas sayaclar
# (sherlock=1710, contests=301, protokol=17) dogal olarak ayni kaldi ve bekci SARI verdi.
# Bu FAKE-RED'di (kural-5): "3 kosu" saymak kadanstan bagimsizdir. Dogrusu: donmusluk ancak
# GERCEK ZAMAN gectiginde anlamlidir. 3 haftalik kosu ~14 gune yayilir; suruklenme payiyla
# en az 10 gun sarti konur => ayni-gun/ardisik-gun tekrarlari ASLA alarm uretmez.
DONMUS_MIN_YAYILIM_GUN = 10

KAYITLI_UC = 10

# TASIYICI SAYI — her ucun "bu satir bos mu dolu mu"yu belirleyen tek sayisi.
# Hepsi 2026-08-18 kosusundan OLCULDU; hicbiri bugun 0 degil (en kucugu 17),
# dolayisiyla 0/None = sema kirildi demektir (mesru-0 senaryosu yok).
def _topla(ozet, alan):
    """Ic-sozluklerdeki `alan`i toplar (npm/pypi/github ic ice paket sozlugu tasir)."""
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
    """Uc bacagi da olcer. Doner: (kod, rapor_dict). Kod: 0 yesil / 1 sari / 2 kirmizi."""
    simdi = simdi or datetime.now(timezone.utc)
    r = {"seri": str(seri), "olcum_utc": simdi.isoformat(timespec="seconds"),
         "bulgular": [], "sev": "YESIL"}
    kirmizi, sari = [], []

    rows = kayitlar(seri)
    r["kayit_sayisi"] = len(rows)
    if not rows:
        r["bulgular"].append("KIRMIZI seri BOS veya YOK: %s" % seri)
        r["sev"] = "KIRMIZI"
        return 2, r

    # ── (1) TAZELIK ─────────────────────────────────────────────────────────
    damgalar = sorted({x.get("zaman_utc", "") for x in rows if x.get("zaman_utc")})
    son_damga = damgalar[-1] if damgalar else None
    r["son_kayit_utc"] = son_damga
    r["kosu_sayisi"] = len(damgalar)
    yas = _yas_gun(son_damga, simdi) if son_damga else None
    r["kayit_yasi_gun"] = round(yas, 3) if yas is not None else None
    # dosya mtime AYRICA raporlanir (dokunuldu-ama-yazilmadi ayrimi icin) — hukum KAYITTAN
    try:
        r["dosya_mtime_yasi_gun"] = round(
            (simdi - datetime.fromtimestamp(seri.stat().st_mtime, timezone.utc)).total_seconds() / 86400.0, 3)
    except Exception:
        r["dosya_mtime_yasi_gun"] = None

    if yas is None:
        kirmizi.append("son kayit damgasi OKUNAMADI (zaman_utc yok/bozuk)")
    elif yas > TAZELIK_KIRMIZI_GUN:
        kirmizi.append("BAYAT: son kayit %.1f gun once (kirmizi esik %d g = 2 kadans; "
                       "kacan hafta rolling-uclarda GERI URETILEMEZ)" % (yas, TAZELIK_KIRMIZI_GUN))
    elif yas > TAZELIK_SARI_GUN:
        sari.append("gecikme: son kayit %.1f gun once (sari esik %d g = kadans+pay)"
                    % (yas, TAZELIK_SARI_GUN))

    # ── son kosunun kayitlari ───────────────────────────────────────────────
    son_kosu = [x for x in rows if x.get("zaman_utc") == son_damga]
    r["son_kosu_uc_sayisi"] = len(son_kosu)

    # ── (+) EKSIK-UC ────────────────────────────────────────────────────────
    if len(son_kosu) < KAYITLI_UC:
        eksikler = sorted(set(TASIYICILAR) - {x.get("uc") for x in son_kosu})
        kirmizi.append("EKSIK-UC: son kosuda %d/%d uc var; dusenler=%s"
                       % (len(son_kosu), KAYITLI_UC, ",".join(eksikler) or "?"))

    # ── (2) SIFIR/NONE + durum ──────────────────────────────────────────────
    tasiyici_son = {}
    for k in son_kosu:
        uc = k.get("uc", "?")
        durum = k.get("durum")
        if durum and durum != "OK":
            kirmizi.append("UC-HATA: %s durum=%s" % (uc, durum))
        cikar = TASIYICILAR.get(uc)
        if cikar is None:
            continue
        deger = cikar(k.get("ozet"))
        tasiyici_son[uc] = deger
        if deger is None:
            kirmizi.append("SESSIZ-NONE: %s tasiyici sayisi YOK (sema kirildi)" % uc)
        elif deger == 0:
            kirmizi.append("SESSIZ-SIFIR: %s tasiyici sayisi 0 (sema kirildi; "
                           "2026-08-18 olcumunde en kucuk tasiyici 17 idi)" % uc)
    r["tasiyici_son_kosu"] = tasiyici_son

    # ── (3) DONMUS SERI ─────────────────────────────────────────────────────
    donmus = {}
    for uc, cikar in TASIYICILAR.items():
        dizi, dizi_ts = [], []
        for d in damgalar[::-1]:                      # yeniden eskiye
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
        # ZAMAN-YAYILIMI sarti: ayni-gun tekrarlari donmusluk DEGILDIR (fake-red freni)
        yayilim = 0.0
        if n >= 2:
            y = _yas_gun(dizi_ts[n - 1], simdi)
            e = _yas_gun(dizi_ts[0], simdi)
            if y is not None and e is not None:
                yayilim = y - e
        if n >= DONMUS_ESIK and yayilim >= DONMUS_MIN_YAYILIM_GUN:
            sari.append("DONMUS: %s son %d kosuda ayni deger (%s), %.1f gune yayilmis; "
                        "esik=%d kosu & %d gun [n=2-kosu kalibrasyon borcu var]"
                        % (uc, n, dizi[0], yayilim, DONMUS_ESIK, DONMUS_MIN_YAYILIM_GUN))
    r["ardisik_ayni"] = donmus

    r["bulgular"] = ["KIRMIZI " + x for x in kirmizi] + ["SARI " + x for x in sari]
    if kirmizi:
        r["sev"] = "KIRMIZI"
        return 2, r
    if sari:
        r["sev"] = "SARI"
        return 1, r
    r["bulgular"].append("YESIL taze(%.2fg) · %d/%d uc dolu · donmus-yok"
                         % (yas or 0, len(tasiyici_son), KAYITLI_UC))
    return 0, r


def deftere_yaz(defter: Path, r: dict, kod: int):
    if kod == 0:
        return
    kayit = {"ts": r["olcum_utc"], "source": "ai-arz-tazelik",
             "sev": "CRITICAL" if kod == 2 else "WARN",
             "dedup_key": "ai-arz|tazelik|%s" % r["sev"],
             "konu": "ai-arz-toplayici", "sinif": "AI_ARZ_%s" % r["sev"],
             "msg": " | ".join(r["bulgular"])[:600],
             "meta": {"kayit_yasi_gun": r.get("kayit_yasi_gun"),
                      "son_kosu_uc_sayisi": r.get("son_kosu_uc_sayisi"),
                      "tasiyici": r.get("tasiyici_son_kosu")}}
    defter.parent.mkdir(parents=True, exist_ok=True)
    with open(defter, "a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# KURAL-4 OZ-TESTI — bekci ONCE KENDINI isirir
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
    """kosular: [(ts, {uc: ozet}, durum_override)]"""
    with open(yol, "w", encoding="utf-8") as f:
        for ts, ucler, durumlar in kosular:
            for uc, ozet in ucler.items():
                f.write(_satir(ts, uc, ozet, durumlar.get(uc, "OK")) + "\n")


def _kaydir(ozetler, artis):
    """Buyuyen sayaclari taklit et (donmus-alarmi tetiklememek icin)."""
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
    tmp = Path(tempfile.mkdtemp(prefix="ai-arz-oztest-"))
    gecti, kaldi = 0, 0

    def kos(ad, kosular, beklenen, simdi_=simdi):
        nonlocal gecti, kaldi
        yol = tmp / (ad + ".ndjson")
        _seri_yaz(yol, kosular)
        kod, r = denetle(yol, simdi_)
        ad_bek = {0: "YESIL", 1: "SARI", 2: "KIRMIZI"}
        ok = kod == beklenen
        gecti += ok
        kaldi += (not ok)
        print("  [%s] %-22s beklenen=%-7s olculen=%-7s" % ("GECTI" if ok else "KALDI",
              ad, ad_bek[beklenen], ad_bek[kod]))
        for b in r["bulgular"][:2]:
            print("          %s" % b[:118])
        return ok

    def gun_once(n):
        return (simdi - timedelta(days=n)).isoformat(timespec="seconds")

    print("KURAL-4 OZ-TESTI — bekci once KENDINI isiriyor")
    print("  esikler: TAZELIK sari=%dg kirmizi=%dg · DONMUS=%d · KAYITLI_UC=%d"
          % (TAZELIK_SARI_GUN, TAZELIK_KIRMIZI_GUN, DONMUS_ESIK, KAYITLI_UC))
    print()

    # 1) SAGLIKLI: taze + dolu + degisen => YESIL
    kos("saglikli", [(gun_once(14), _kaydir(_SAGLAM, -20), {}),
                     (gun_once(7), _kaydir(_SAGLAM, -10), {}),
                     (gun_once(1), _SAGLAM, {})], 0)

    # 2) SAHTE-BAYAT: icerik saglam ama 30 gun once => KIRMIZI
    kos("sahte-bayat", [(gun_once(44), _kaydir(_SAGLAM, -20), {}),
                        (gun_once(37), _kaydir(_SAGLAM, -10), {}),
                        (gun_once(30), _SAGLAM, {})], 2)

    # 3) SINIR-GECIKME: 9 gun (sari band) => SARI
    kos("sinir-gecikme", [(gun_once(23), _kaydir(_SAGLAM, -20), {}),
                          (gun_once(16), _kaydir(_SAGLAM, -10), {}),
                          (gun_once(9), _SAGLAM, {})], 1)

    # 4) SAHTE-SIFIR: taze ama bir uc 0 doner (sema kirildi) => KIRMIZI
    bozuk = dict(_SAGLAM); bozuk["sherlock_leaderboard"] = {"arastirmaci_sayisi": 0}
    kos("sahte-sifir", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                        (gun_once(1), bozuk, {})], 2)

    # 5) SAHTE-NONE: alan adi degisti (sessiz None) => KIRMIZI
    bozuk2 = dict(_SAGLAM); bozuk2["x402_discovery"] = {"resource_count": 15095}
    kos("sahte-none", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                       (gun_once(1), bozuk2, {})], 2)

    # 6) DONMUS: taze + dolu ama 3 kosu ayni deger, 14 gune YAYILMIS => SARI
    kos("donmus-seri", [(gun_once(15), _SAGLAM, {}),
                        (gun_once(8), _SAGLAM, {}),
                        (gun_once(1), _SAGLAM, {})], 1)

    # 6b) FAKE-RED FRENI [canli-vaka 2026-08-18T15:05Z]: AYNI GUN 3 kosu, yavas sayaclar
    #     dogal olarak ayni => donmusluk DEGIL => YESIL kalmali.
    ayni_gun = [((simdi - timedelta(hours=8)).isoformat(timespec="seconds"), _SAGLAM, {}),
                ((simdi - timedelta(hours=7)).isoformat(timespec="seconds"), _SAGLAM, {}),
                ((simdi - timedelta(hours=1)).isoformat(timespec="seconds"), _SAGLAM, {})]
    kos("ayni-gun-3-kosu", ayni_gun, 0)

    # 7) EKSIK-UC: son kosuda 10 yerine 8 uc => KIRMIZI
    eksik = {k: v for k, v in list(_SAGLAM.items())[:8]}
    kos("eksik-uc", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                     (gun_once(1), eksik, {})], 2)

    # 8) UC-HATA: durum != OK => KIRMIZI
    kos("uc-hata", [(gun_once(8), _kaydir(_SAGLAM, -10), {}),
                    (gun_once(1), _SAGLAM, {"apify_store": "HTTP-HATA"})], 2)

    # 9) BOS SERI => KIRMIZI
    bos = tmp / "bos.ndjson"; bos.write_text("", encoding="utf-8")
    kod, _ = denetle(bos, simdi)
    ok = kod == 2
    gecti += ok; kaldi += (not ok)
    print("  [%s] %-22s beklenen=KIRMIZI olculen=%s" % ("GECTI" if ok else "KALDI",
          "bos-seri", {0: "YESIL", 1: "SARI", 2: "KIRMIZI"}[kod]))

    print()
    print("OZ-TEST SONUC: %d gecti / %d kaldi" % (gecti, kaldi))
    return 0 if kaldi == 0 else 1


def main():
    ap = argparse.ArgumentParser(description="AI-arz toplayici tazelik/dolu-luk bekcisi")
    ap.add_argument("--seri", default=str(VARSAYILAN_SERI))
    ap.add_argument("--defter", default="", help="alarm ndjson (bos=yazma)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--oz-test", action="store_true", help="KURAL-4: once kendini isir")
    a = ap.parse_args()

    if a.oz_test:
        return oz_test()

    kod, r = denetle(Path(a.seri))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print("AI-ARZ TAZELIK BEKCISI — %s" % r["sev"])
        print("  seri=%s kayit=%s kosu=%s" % (r["seri"], r.get("kayit_sayisi"), r.get("kosu_sayisi")))
        print("  son kayit=%s (yas %.2f gun) · dosya-mtime yasi=%s gun"
              % (r.get("son_kayit_utc"), r.get("kayit_yasi_gun") or -1, r.get("dosya_mtime_yasi_gun")))
        for b in r["bulgular"]:
            print("  - %s" % b)
    if a.defter:
        deftere_yaz(Path(a.defter), r, kod)
    return kod


if __name__ == "__main__":
    sys.exit(main())
