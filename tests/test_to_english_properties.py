"""Property tests for to_english.cevir() on random nested structures built from the keys that
harita_yukle() loads (random.Random with fixed seeds, a few hundred structures per property)."""
import copy
import random

import pytest

import to_english as te

META, KEYS = te.harita_yukle()
TR = sorted(KEYS)
PAKET_UC = META["passthrough"]["package_identifiers"]["endpoints"]
BILINMEYEN = ["bilinmeyen_alan", "yeni_sayac", "extra", "@scope/pkg", "owner/repo"]
UCLAR = PAKET_UC + ["x402_discovery", "hf_models", "sherlock_contests"]
TEKRAR = 300


def yaprak(rnd):
    return rnd.choice([0, 1, -3, 2.5, 0.0, True, False, None, "", "metin", "ç", "2026-08-18T07:00:00+00:00"])


def anahtar(rnd):
    return rnd.choice(BILINMEYEN) if rnd.random() < 0.08 else rnd.choice(TR)


def dugum(rnd, derinlik):
    secim = rnd.random()
    if derinlik <= 0 or secim < 0.35:
        return yaprak(rnd)
    if secim < 0.5:
        return [dugum(rnd, derinlik - 1) for _ in range(rnd.randint(0, 3))]
    d = {}
    for _ in range(rnd.randint(0, 5)):
        k = anahtar(rnd)
        if rnd.random() < 0.08:
            d["histogram"] = {rnd.choice(["<1", "1-10", ">=10000", "n", "ozet"]): rnd.randint(0, 9)
                              for _ in range(rnd.randint(0, 3))}
        else:
            d[k] = dugum(rnd, derinlik - 1)
    return d


def kayit(rnd):
    uc = rnd.choice(UCLAR)
    r = {"zaman_utc": "2026-08-18T07:00:00+00:00", "uc": uc}
    if uc in PAKET_UC:
        r["ozet"] = {rnd.choice(["@anthropic-ai/sdk", "ozet", "kaynak_sayisi", "a/b"]) + str(i): dugum(rnd, 2)
                     for i in range(rnd.randint(0, 3))}
    else:
        r["ozet"] = dugum(rnd, 4)
    if rnd.random() < 0.3:
        r[anahtar(rnd)] = dugum(rnd, 2)
    return uc, r


def kayitlar(tohum):
    rnd = random.Random(tohum)
    return [kayit(rnd) for _ in range(TEKRAR)]


# ── reference: expected output, unknown keys and collisions ─────────────────
def beklenen(d, uc, yol, eksik):
    """Returns the expected converted value, or raises te.AdCakismasi."""
    if isinstance(d, list):
        return [beklenen(x, uc, yol, eksik) for x in d]
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        veri = (yol and yol[-1] == "histogram") or (yol == ["ozet"] and uc in PAKET_UC)
        if veri:
            yeni = k
        elif k in KEYS:
            yeni = KEYS[k]
        else:
            yeni = k
            eksik.append({"key": k, "endpoint": uc, "path": "/".join(yol) or "<root>"})
        if yeni in out:
            raise te.AdCakismasi(yeni)
        out[yeni] = beklenen(v, uc, yol + [k], eksik)
    return out


def yapraklar(d, yol=()):
    """(position, value) for every leaf; the position uses list indexes and key order."""
    if isinstance(d, dict):
        out = []
        for i, v in enumerate(d.values()):
            out += yapraklar(v, yol + (("k", i),))
        return out
    if isinstance(d, list):
        out = []
        for i, v in enumerate(d):
            out += yapraklar(v, yol + (("i", i),))
        return out
    return [(yol, d)]


def cevir_veya_hata(r, uc):
    eksik = []
    try:
        return te.cevir(r, uc, [], KEYS, META, eksik), eksik, None
    except te.AdCakismasi as e:
        return None, eksik, e


def beklenen_veya_hata(r, uc):
    eksik = []
    try:
        return beklenen(r, uc, [], eksik), eksik, None
    except te.AdCakismasi as e:
        return None, eksik, e


# ── properties ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tohum", [1, 2, 3])
def test_conversion_matches_the_reference_including_collisions(tohum):
    for uc, r in kayitlar(tohum):
        out, eksik, hata = cevir_veya_hata(r, uc)
        b_out, b_eksik, b_hata = beklenen_veya_hata(r, uc)
        assert (hata is None) == (b_hata is None)
        if hata is None:
            assert out == b_out and eksik == b_eksik


@pytest.mark.parametrize("tohum", [4, 5])
def test_every_leaf_stays_unchanged_and_in_place(tohum):
    for uc, r in kayitlar(tohum):
        out, _, hata = cevir_veya_hata(r, uc)
        if hata is None:
            once, sonra = yapraklar(r), yapraklar(out)
            assert [p for p, _ in once] == [p for p, _ in sonra]
            assert all(a is b or (a == b and type(a) is type(b)) for (_, a), (_, b) in zip(once, sonra))


@pytest.mark.parametrize("tohum", [6, 7])
def test_only_keys_change(tohum):
    def iskelet(d):
        if isinstance(d, dict):
            return ("dict", [iskelet(v) for v in d.values()])
        if isinstance(d, list):
            return ("list", [iskelet(v) for v in d])
        return "leaf"
    for uc, r in kayitlar(tohum):
        out, _, hata = cevir_veya_hata(r, uc)
        if hata is None:
            assert iskelet(out) == iskelet(r)


def yolda_var(d, yol, k):
    """True when key `k` sits in an object reached by following the "/"-joined path `yol`.
    Lists are walked through; a key along the way may itself contain "/"."""
    if isinstance(d, list):
        return any(yolda_var(x, yol, k) for x in d)
    if not isinstance(d, dict):
        return False
    if yol == "":
        return k in d
    return any(yolda_var(v, yol[len(a) + 1:] if yol != a else "", k)
               for a, v in d.items() if yol == a or yol.startswith(a + "/"))


@pytest.mark.parametrize("tohum", [8, 9])
def test_known_keys_get_their_english_name_and_unknown_keys_are_reported_with_their_path(tohum):
    for uc, r in kayitlar(tohum):
        out, eksik, hata = cevir_veya_hata(r, uc)
        if hata is not None:
            continue
        assert list(out) == [KEYS.get(k, k) for k in r]
        for e in eksik:
            assert e["endpoint"] == uc and e["key"] not in KEYS
            assert yolda_var(r, "" if e["path"] == "<root>" else e["path"], e["key"]), e


@pytest.mark.parametrize("tohum", [10, 11])
def test_input_is_not_modified(tohum):
    for uc, r in kayitlar(tohum):
        kopya = copy.deepcopy(r)
        cevir_veya_hata(r, uc)
        assert r == kopya


def test_collision_is_raised_when_two_keys_in_one_object_share_an_english_name():
    ciftler = {}
    for tr, en in KEYS.items():
        ciftler.setdefault(en, []).append(tr)
    for en, trs in ciftler.items():
        if len(trs) > 1:
            with pytest.raises(te.AdCakismasi):
                te.cevir({trs[0]: 1, trs[1]: 2}, "x402_discovery", ["ozet"], KEYS, META, [])
