"""Property tests for collector.yuzdelik and collector.dagilim_ozeti. Inputs are generated with
random.Random and fixed seeds, a few hundred per property, standard library only."""
import math
import random

import pytest

import collector as c

PCT = (10, 25, 50, 75, 90, 95, 99)
KOVALAR = [1, 10, 100, 1000]
TEKRAR = 300


def sayilar(rnd, en_az=0, negatif=True):
    """A list of finite ints and floats with zeros, repeats and a wide range of sizes."""
    n = rnd.randint(en_az, 40)
    out = []
    for _ in range(n):
        tur = rnd.random()
        if tur < 0.15:
            out.append(0 if rnd.random() < 0.5 else 0.0)
        elif tur < 0.3 and out:
            out.append(rnd.choice(out))
        elif tur < 0.6:
            out.append(rnd.randint(-1000 if negatif else 0, 10 ** rnd.randint(1, 9)))
        else:
            out.append(rnd.uniform(-50 if negatif else 0, 10 ** rnd.uniform(-3, 7)))
    return out


def karisik(rnd):
    """Numbers mixed with values that are not int or float."""
    out = sayilar(rnd)
    for _ in range(rnd.randint(0, 6)):
        out.insert(rnd.randint(0, len(out)), rnd.choice([None, "3", "0", [], {}, [1], {"n": 1}, b"1"]))
    return out


def girdiler(tohum, uret=sayilar, **k):
    rnd = random.Random(tohum)
    return [uret(rnd, **k) for _ in range(TEKRAR)]


# ── yuzdelik ────────────────────────────────────────────────────────────────
def test_percentile_of_empty_input_is_none():
    assert all(c.yuzdelik([], p) is None for p in (0, 50, 100))


@pytest.mark.parametrize("tohum", [1, 2])
def test_percentile_is_an_element_and_splits_the_data_at_rank_p(tohum):
    rnd = random.Random(tohum)
    for d in girdiler(tohum, en_az=1):
        d = sorted(d)
        p = rnd.uniform(0, 100)
        v = c.yuzdelik(d, p)
        assert v in d
        n = len(d)
        assert sum(1 for x in d if x <= v) >= math.ceil(p / 100 * n)
        assert sum(1 for x in d if x >= v) >= n - max(1, math.ceil(p / 100 * n)) + 1


@pytest.mark.parametrize("tohum", [3, 4])
def test_percentile_never_decreases_as_p_grows(tohum):
    for d in girdiler(tohum, en_az=1):
        d = sorted(d)
        degerler = [c.yuzdelik(d, p) for p in range(0, 101)]
        assert degerler == sorted(degerler)
        assert degerler[0] == d[0] and degerler[-1] == d[-1]


# ── dagilim_ozeti ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("tohum", [5, 6])
def test_n_counts_only_int_and_float_items(tohum):
    for d in girdiler(tohum, uret=karisik):
        o = c.dagilim_ozeti(d, KOVALAR)
        assert o["n"] == sum(1 for x in d if isinstance(x, (int, float)))


def test_input_without_numbers_gives_only_n_zero():
    rnd = random.Random(7)
    assert c.dagilim_ozeti([], KOVALAR) == {"n": 0}
    for _ in range(TEKRAR):
        d = [rnd.choice([None, "3", [], {}, b"1"]) for _ in range(rnd.randint(0, 10))]
        assert c.dagilim_ozeti(d, KOVALAR) == {"n": 0}


@pytest.mark.parametrize("tohum", [8, 9])
def test_percentiles_never_decrease_from_p10_to_p99(tohum):
    for d in girdiler(tohum, en_az=1):
        o = c.dagilim_ozeti(d, KOVALAR)
        degerler = [o["p%d" % p] for p in PCT]
        assert degerler == sorted(degerler)


@pytest.mark.parametrize("tohum", [10, 11])
def test_every_percentile_is_an_input_rounded_to_four_decimals(tohum):
    for d in girdiler(tohum, en_az=1):
        o = c.dagilim_ozeti(d, KOVALAR)
        yuvarlak = {round(float(x), 4) for x in d}
        assert all(o["p%d" % p] in yuvarlak for p in PCT)


@pytest.mark.parametrize("tohum", [12, 13])
def test_zero_count_counts_exact_zeros(tohum):
    for d in girdiler(tohum, uret=karisik):
        o = c.dagilim_ozeti(d, KOVALAR)
        if o["n"]:
            assert o["sifir_sayisi"] == sum(1 for x in d if isinstance(x, (int, float)) and x == 0)


@pytest.mark.parametrize("tohum", [14, 15])
def test_total_and_maximum_are_the_rounded_sum_and_max(tohum):
    for d in girdiler(tohum, en_az=1):
        o = c.dagilim_ozeti(d, KOVALAR)
        f = sorted(float(x) for x in d)
        assert o["toplam"] == round(sum(f), 2) and o["maks"] == round(f[-1], 2)


@pytest.mark.parametrize("tohum", [16, 17])
def test_histogram_counts_add_up_to_n(tohum):
    for d in girdiler(tohum, en_az=1):
        o = c.dagilim_ozeti(d, KOVALAR)
        assert sum(o["histogram"].values()) == o["n"]
        assert list(o["histogram"]) == ["<1", "1-10", "10-100", "100-1000", ">=1000"]


@pytest.mark.parametrize("tohum", [18, 19])
def test_share_keys_are_present_exactly_when_the_rounded_total_is_positive(tohum):
    for d in girdiler(tohum, en_az=1):
        o = c.dagilim_ozeti(d, KOVALAR)
        var = "top1_pay" in o
        assert var == ("top10_pay" in o) == (o["toplam"] > 0)


def test_share_keys_are_absent_when_every_value_is_zero():
    rnd = random.Random(20)
    for _ in range(TEKRAR):
        d = [rnd.choice([0, 0.0]) for _ in range(rnd.randint(1, 30))]
        o = c.dagilim_ozeti(d, KOVALAR)
        assert o["toplam"] == 0 and "top1_pay" not in o and "top10_pay" not in o


@pytest.mark.parametrize("tohum", [21, 22])
def test_top_one_share_never_exceeds_top_ten_share_for_non_negative_values(tohum):
    for d in girdiler(tohum, en_az=1, negatif=False):
        o = c.dagilim_ozeti(d, KOVALAR)
        if "top1_pay" in o:
            assert 0 <= o["top1_pay"] <= o["top10_pay"]


@pytest.mark.parametrize("tohum", [23, 24])
def test_summary_does_not_depend_on_input_order(tohum):
    rnd = random.Random(tohum)
    for d in girdiler(tohum, uret=karisik):
        k = list(d)
        rnd.shuffle(k)
        assert c.dagilim_ozeti(k, KOVALAR) == c.dagilim_ozeti(d, KOVALAR)


@pytest.mark.parametrize("tohum", [25, 26])
def test_ignored_items_do_not_change_the_summary(tohum):
    rnd = random.Random(tohum)
    for d in girdiler(tohum, en_az=1):
        k = list(d)
        for _ in range(rnd.randint(1, 5)):
            k.insert(rnd.randint(0, len(k)), rnd.choice([None, "7", [], {}]))
        assert c.dagilim_ozeti(k, KOVALAR) == c.dagilim_ozeti(d, KOVALAR)
