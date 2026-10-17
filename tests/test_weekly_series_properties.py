"""Property tests for weekly() in examples/weekly_series.py. Random series (random.Random with
fixed seeds) are compared with a small reference implementation written out in this file."""
import importlib.util
import random
from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("weekly_series", KOK / "examples" / "weekly_series.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

TEKRAR = 300
ILK_GUN = datetime(2026, 8, 17, tzinfo=timezone.utc)          # Monday of 2026-W34


# ── reference implementation ────────────────────────────────────────────────
def ref_number(v):
    return v if type(v) in (int, float) else None


def ref_read(uc, ozet):
    if uc == "x402_discovery":
        return ref_number(ozet.get("kaynak_sayisi"))
    if uc == "sherlock_contests":
        return ref_number(ozet.get("acik_yarisma"))
    if uc == "hf_models":
        inner = ozet.get("indirme_dagilimi")
        return ref_number(inner.get("toplam")) if isinstance(inner, dict) else None
    if uc == "npm_downloads":
        found = []
        for sub in ozet.values():
            if isinstance(sub, dict) and ref_number(sub.get("toplam_30g")) is not None:
                found.append(sub["toplam_30g"])
        return sum(found) if found else None
    return None


def ref_usable_value(row):
    if row.get("durum") != "OK":
        return None
    ozet = row.get("ozet")
    if not isinstance(ozet, dict) or "olculemedi" in ozet:
        return None
    for sub in ozet.values():
        if isinstance(sub, dict) and ("hata" in sub or "olculemedi" in sub):
            return None
    return ref_read(row["uc"], ozet)


def ref_week(stamp):
    y, w, _ = datetime.fromisoformat(stamp).isocalendar()
    return "%d-W%02d" % (y, w)


def ref_weekly(rows):
    rows = [r for r in rows if isinstance(r.get("zaman_utc"), str) and isinstance(r.get("uc"), str)]
    if not rows:
        return []
    last = max(ref_week(r["zaman_utc"]) for r in rows)
    out = []
    for name in sorted({r["uc"] for r in rows if r["uc"] in ws.VALUES}):
        mine = [r for r in rows if r["uc"] == name]
        week = min(ref_week(r["zaman_utc"]) for r in mine)
        while True:
            in_week = [r for r in mine if ref_week(r["zaman_utc"]) == week]
            good = [r for r in in_week if ref_usable_value(r) is not None]
            if good:
                latest = max(good, key=lambda r: r["zaman_utc"])
                out.append({"week": week, "endpoint": name, "value": ref_usable_value(latest),
                            "zaman_utc": latest["zaman_utc"]})
            else:
                out.append({"week": week, "endpoint": name, "value": None,
                            "gap": "rows present, none usable" if in_week else "no rows"})
            if week == last:
                break
            y, w = (int(x) for x in week.split("-W"))
            week = "%d-W%02d" % (date.fromisocalendar(y, w, 1) + timedelta(days=7)).isocalendar()[:2]
    out.sort(key=lambda e: (e["week"], e["endpoint"]))
    return out


# ── generated series ────────────────────────────────────────────────────────
UCLAR = ["x402_discovery", "sherlock_contests", "hf_models", "npm_downloads", "unknown_endpoint"]
DURUMLAR = ["OK", "OK", "OK", "OK", "HATA", "HTTP-HATA", "HATA-ICERIDE", None]


def ozet_uret(rnd, uc):
    sayi = rnd.choice([0, 0.0, 1, 17, 475, 1580224158, 3.25, True, None, "12"])
    secim = rnd.random()
    if uc == "npm_downloads":
        ozet = {"pkg%d" % i: {"toplam_30g": rnd.choice([0, 5, 120000, 2.5, None])} for i in range(rnd.randint(0, 3))}
        if secim < 0.15 and ozet:
            ozet[rnd.choice(list(ozet))]["hata"] = "HTTPError 429"
        elif secim < 0.25 and ozet:
            ozet[rnd.choice(list(ozet))]["olculemedi"] = "no numeric downloads"
    elif uc == "hf_models":
        ozet = {"indirme_dagilimi": rnd.choice([{"toplam": sayi}, {"n": 0}, None])}
    else:
        ozet = {"kaynak_sayisi" if uc == "x402_discovery" else "acik_yarisma": sayi}
    if rnd.random() < 0.1:
        ozet["olculemedi"] = "schema broken"
    return rnd.choice([ozet] * 9 + [None, "x"])


def seri_uret(rnd):
    hafta_sayisi = rnd.randint(1, 9)
    bos = {h for h in range(hafta_sayisi) if rnd.random() < 0.3}
    saatler = rnd.sample(range(hafta_sayisi * 7 * 24), min(hafta_sayisi * 7 * 24, rnd.randint(0, 40)))
    rows = []
    for s in saatler:
        if s // (7 * 24) in bos:
            continue
        stamp = (ILK_GUN + timedelta(hours=s, minutes=rnd.randint(0, 59))).isoformat(timespec="seconds")
        uc = rnd.choice(UCLAR)
        row = {"zaman_utc": stamp, "uc": uc}
        durum = rnd.choice(DURUMLAR)
        if durum is not None:
            row["durum"] = durum
        ozet = ozet_uret(rnd, uc)
        if ozet is not None:
            row["ozet"] = ozet
        rows.append(row)
    if rnd.random() < 0.1:
        rows.append({"zaman_utc": 123, "uc": "x402_discovery", "durum": "OK", "ozet": {"kaynak_sayisi": 9}})
    return rows


def seriler(tohum):
    rnd = random.Random(tohum)
    return [seri_uret(rnd) for _ in range(TEKRAR)]


# ── properties ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tohum", [1, 2, 3])
def test_weekly_matches_the_reference(tohum):
    for rows in seriler(tohum):
        assert ws.weekly(rows) == ref_weekly(rows)


@pytest.mark.parametrize("tohum", [4, 5])
def test_a_gap_is_never_a_number(tohum):
    for rows in seriler(tohum):
        for e in ws.weekly(rows):
            if "gap" in e:
                assert e["value"] is None and "zaman_utc" not in e
            else:
                assert type(e["value"]) in (int, float)


@pytest.mark.parametrize("tohum", [6, 7])
def test_each_endpoint_has_one_entry_per_week_without_holes(tohum):
    for rows in seriler(tohum):
        sonuc = ws.weekly(rows)
        for name in {e["endpoint"] for e in sonuc}:
            haftalar = [e["week"] for e in sonuc if e["endpoint"] == name]
            assert len(haftalar) == len(set(haftalar))
            assert haftalar == ws._weeks(haftalar[0], haftalar[-1])
            assert haftalar[-1] == max(e["week"] for e in sonuc)


@pytest.mark.parametrize("tohum", [8, 9])
def test_a_value_comes_from_the_latest_usable_row_of_its_week(tohum):
    for rows in seriler(tohum):
        for e in ws.weekly(rows):
            if "gap" in e:
                continue
            kaynak = [r for r in rows if r.get("zaman_utc") == e["zaman_utc"] and r.get("uc") == e["endpoint"]]
            assert len(kaynak) == 1 and ref_usable_value(kaynak[0]) == e["value"]
            assert ref_week(e["zaman_utc"]) == e["week"]
            sonra = [r for r in rows if isinstance(r.get("zaman_utc"), str) and r.get("uc") == e["endpoint"]
                     and ref_week(r["zaman_utc"]) == e["week"] and r["zaman_utc"] > e["zaman_utc"]]
            assert all(ref_usable_value(r) is None for r in sonra)


@pytest.mark.parametrize("tohum", [10, 11])
def test_row_order_does_not_change_the_result(tohum):
    rnd = random.Random(tohum)
    for rows in seriler(tohum):
        karisik = list(rows)
        rnd.shuffle(karisik)
        assert ws.weekly(karisik) == ws.weekly(rows)


@pytest.mark.parametrize("tohum", [12, 13])
def test_selecting_one_endpoint_gives_its_entries_from_the_full_result(tohum):
    for rows in seriler(tohum):
        hepsi = ws.weekly(rows)
        for name in {e["endpoint"] for e in hepsi}:
            assert ws.weekly(rows, [name]) == [e for e in hepsi if e["endpoint"] == name]


@pytest.mark.parametrize("tohum", [14, 15])
def test_unusable_rows_never_change_the_values(tohum):
    rnd = random.Random(tohum)
    for rows in seriler(tohum):
        ek = []
        for r in rows:
            if isinstance(r.get("zaman_utc"), str) and r.get("uc") in ws.VALUES and rnd.random() < 0.3:
                bozuk = dict(r, durum=rnd.choice(["HATA", "HTTP-HATA"]))
                ek.append(bozuk)
        if not ek:
            continue
        once = {(e["week"], e["endpoint"]): e.get("value") for e in ws.weekly(rows)}
        sonra = {(e["week"], e["endpoint"]): e.get("value") for e in ws.weekly(rows + ek)}
        assert once == sonra
