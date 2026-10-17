"""Checks on every distribution summary in the published series: the objects the collector's
dagilim_ozeti() writes (n, toplam, sifir_sayisi, p10..p99, maks, histogram, top1_pay, top10_pay).
Each summary must be internally consistent; the file is only read."""
import json
import math
import re

import pytest

from conftest import KOK

PCT = ["p10", "p25", "p50", "p75", "p90", "p95", "p99"]
TAM = {"n", "toplam", "sifir_sayisi", *PCT, "maks", "histogram", "top1_pay", "top10_pay"}
PAYSIZ = TAM - {"top1_pay", "top10_pay"}


def ozetler():
    """(line number, endpoint, path, summary) for every object that carries n and p50."""
    out = []
    satirlar = (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()

    def gez(o, no, uc, yol):
        if isinstance(o, dict):
            if "n" in o and "p50" in o:
                out.append((no, uc, "/".join(yol), o))
            for k, v in o.items():
                gez(v, no, uc, yol + [k])
        elif isinstance(o, list):
            for v in o:
                gez(v, no, uc, yol)
    for no, s in enumerate(satirlar, 1):
        if s.strip():
            r = json.loads(s)
            gez(r.get("ozet"), no, r.get("uc"), ["ozet"])
    return out


OZETLER = ozetler()
KIMLIK = ["%d:%s:%s" % (no, uc, yol) for no, uc, yol, _ in OZETLER]


def test_the_series_has_distribution_summaries():
    assert len(OZETLER) >= 100


@pytest.mark.parametrize("no,uc,yol,o", OZETLER, ids=KIMLIK)
def test_summary_is_internally_consistent(no, uc, yol, o):
    assert set(o) in (TAM, PAYSIZ), sorted(o)
    n = o["n"]
    assert type(n) is int and n >= 1
    sayilar = [o["toplam"], o["maks"], *[o[p] for p in PCT]]
    assert all(type(x) in (int, float) and math.isfinite(x) for x in sayilar)

    # percentiles run upwards and stay within the maximum
    degerler = [o[p] for p in PCT]
    assert degerler == sorted(degerler) and o["p99"] <= o["maks"]

    # zero count and histogram
    assert type(o["sifir_sayisi"]) is int and 0 <= o["sifir_sayisi"] <= n
    h = o["histogram"]
    assert all(type(v) is int and v >= 0 for v in h.values()) and sum(h.values()) == n
    etiketler = list(h)
    assert re.fullmatch(r"<[0-9.e+]+", etiketler[0]) and re.fullmatch(r">=[0-9.e+]+", etiketler[-1])
    sinirlar = [float(etiketler[0][1:])]
    for e in etiketler[1:-1]:
        a, b = e.split("-", 1)
        assert float(a) == sinirlar[-1]
        sinirlar.append(float(b))
    assert float(etiketler[-1][2:]) == sinirlar[-1] and sinirlar == sorted(sinirlar)
    if sinirlar[0] > 0:
        assert h[etiketler[0]] >= o["sifir_sayisi"]       # zeros fall into the first bucket

    # concentration shares exist exactly when the total is positive and stay within [0, 1]
    assert ("top1_pay" in o) == (o["toplam"] > 0)
    if "top1_pay" in o:
        assert 0 <= o["top1_pay"] <= o["top10_pay"] <= 1
        if n <= 10:
            assert o["top10_pay"] == 1.0

