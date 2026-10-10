"""Property tests for freshness_watchdog.denetle(): random healthy series (random.Random with fixed
seeds) are changed in one way at a time and the verdict is checked. Clock fixed; files in tmp_path."""
import json
import random
from datetime import timedelta

import pytest

import freshness_watchdog as w
from conftest import SIMDI

TEKRAR = 120
YESIL, SARI, KIRMIZI = 0, 1, 2


def saglikli_seri(rnd):
    """Weekly runs with every carrier growing; the newest run is 0.5–7 days old."""
    kosu_sayisi = rnd.randint(1, 6)
    son = rnd.uniform(0.5, 7)
    kosular = []
    for i in range(kosu_sayisi):
        yas = son + 7 * (kosu_sayisi - 1 - i) + rnd.uniform(-0.4, 0.4) * (i < kosu_sayisi - 1)
        ts = (SIMDI - timedelta(days=yas)).isoformat(timespec="seconds")
        kosular.append((ts, w._kaydir(w._SAGLAM, 10 * (i - kosu_sayisi))))
    return kosular


def yaz(tmp_path, kosular, ad):
    yol = tmp_path / ad
    with open(yol, "w", encoding="utf-8") as f:
        for ts, ozetler in kosular:
            for uc, o in ozetler.items():
                f.write(json.dumps({"zaman_utc": ts, "uc": uc, "ozet": o, "durum": "OK"}) + "\n")
    return yol


def seriler(tohum):
    rnd = random.Random(tohum)
    return rnd, [saglikli_seri(rnd) for _ in range(TEKRAR)]


@pytest.mark.parametrize("tohum", [1, 2])
def test_a_healthy_growing_series_is_green(tmp_path, tohum):
    _, hepsi = seriler(tohum)
    for i, kosular in enumerate(hepsi):
        kod, r = w.denetle(yaz(tmp_path, kosular, "s%d.ndjson" % i), SIMDI)
        assert kod == YESIL, r["findings"]


def sifir(uc):
    """A summary for `uc` whose load-bearing number is 0."""
    o = json.loads(json.dumps(w._SAGLAM[uc]))
    hedef = o
    while True:
        k, v = next(iter(hedef.items()))
        if isinstance(v, dict):
            hedef = v
        else:
            hedef[k] = 0
            return o


@pytest.mark.parametrize("tohum", [3, 4])
def test_a_zero_or_missing_carrier_in_the_last_run_is_red(tmp_path, tohum):
    rnd, hepsi = seriler(tohum)
    for i, kosular in enumerate(hepsi):
        ts, son = kosular[-1]
        uc = rnd.choice(sorted(son))
        sifirla = rnd.random() < 0.5
        bozuk = dict(son, **{uc: sifir(uc) if sifirla else rnd.choice([{}, {"yeni_alan": 5}])})
        kod, r = w.denetle(yaz(tmp_path, kosular[:-1] + [(ts, bozuk)], "s%d.ndjson" % i), SIMDI)
        etiket = "SILENT-ZERO: %s" % uc if sifirla else "SILENT-NONE: %s" % uc
        assert kod == KIRMIZI and any(etiket in b for b in r["findings"]), (uc, r["findings"])


@pytest.mark.parametrize("tohum", [5, 6])
def test_dropping_an_endpoint_from_the_last_run_is_red(tmp_path, tohum):
    rnd, hepsi = seriler(tohum)
    for i, kosular in enumerate(hepsi):
        ts, son = kosular[-1]
        dusen = rnd.sample(sorted(son), rnd.randint(1, 3))
        kalan = {k: v for k, v in son.items() if k not in dusen}
        kod, r = w.denetle(yaz(tmp_path, kosular[:-1] + [(ts, kalan)], "s%d.ndjson" % i), SIMDI)
        b = [x for x in r["findings"] if "MISSING-ENDPOINT" in x]
        assert kod == KIRMIZI and b and "dropped=%s" % ",".join(sorted(dusen)) in b[0]


@pytest.mark.parametrize("tohum", [7, 8])
def test_an_error_status_in_the_last_run_is_red(tmp_path, tohum):
    rnd, hepsi = seriler(tohum)
    for i, kosular in enumerate(hepsi):
        yol = yaz(tmp_path, kosular, "s%d.ndjson" % i)
        satirlar = yol.read_text(encoding="utf-8").splitlines()
        son_ts = kosular[-1][0]
        adaylar = [j for j, s in enumerate(satirlar) if json.loads(s)["zaman_utc"] == son_ts]
        j = rnd.choice(adaylar)
        r_ = json.loads(satirlar[j])
        r_["durum"] = rnd.choice(["HATA", "HTTP-HATA", "HATA-ICERIDE"])
        satirlar[j] = json.dumps(r_)
        yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        kod, r = w.denetle(yol, SIMDI)
        assert kod == KIRMIZI and any("ENDPOINT-ERROR: %s" % r_["uc"] in b for b in r["findings"])


@pytest.mark.parametrize("tohum", [9, 10])
def test_moving_the_whole_series_back_in_time_never_improves_the_verdict(tmp_path, tohum):
    rnd, hepsi = seriler(tohum)
    for i, kosular in enumerate(hepsi):
        once, _ = w.denetle(yaz(tmp_path, kosular, "a%d.ndjson" % i), SIMDI)
        kayma = timedelta(days=rnd.uniform(0, 20))
        geri = [((SIMDI.fromisoformat(ts) - kayma).isoformat(timespec="seconds"), o) for ts, o in kosular]
        sonra, _ = w.denetle(yaz(tmp_path, geri, "b%d.ndjson" % i), SIMDI)
        assert sonra >= once


@pytest.mark.parametrize("tohum", [11, 12])
def test_the_verdict_depends_on_the_age_of_the_last_run_only_through_the_thresholds(tmp_path, tohum):
    rnd = random.Random(tohum)
    for i in range(TEKRAR):
        yas = rnd.uniform(0, 30)
        ts = (SIMDI - timedelta(days=yas)).isoformat(timespec="seconds")
        kod, _ = w.denetle(yaz(tmp_path, [(ts, w._SAGLAM)], "s%d.ndjson" % i), SIMDI)
        yas_gercek = w._yas_gun(ts, SIMDI)
        beklenen = KIRMIZI if yas_gercek > w.TAZELIK_KIRMIZI_GUN else SARI if yas_gercek > w.TAZELIK_SARI_GUN else YESIL
        assert kod == beklenen


@pytest.mark.parametrize("tohum", [13, 14])
def test_file_line_order_does_not_change_the_verdict(tmp_path, tohum):
    rnd, hepsi = seriler(tohum)
    for i, kosular in enumerate(hepsi):
        yol = yaz(tmp_path, kosular, "a%d.ndjson" % i)
        kod1, r1 = w.denetle(yol, SIMDI)
        satirlar = yol.read_text(encoding="utf-8").splitlines()
        rnd.shuffle(satirlar)
        yol2 = tmp_path / ("b%d.ndjson" % i)
        yol2.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        kod2, r2 = w.denetle(yol2, SIMDI)
        assert kod1 == kod2
        assert r1["last_run_carriers"] == r2["last_run_carriers"]
        assert r1["consecutive_identical"] == r2["consecutive_identical"]
