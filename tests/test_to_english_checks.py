"""Further checks on to_english.py: the wording of conversion errors and what the built-in
self-test reports for each of its checks. Temporary files go to tmp_path."""
import tempfile

import pytest

import to_english as te
from conftest import KOK

META = {"passthrough": {"package_identifiers": {"endpoints": []}}}


def test_collision_at_the_root_names_the_root_and_the_endpoint():
    keys = {"a": "x", "b": "x"}
    with pytest.raises(te.AdCakismasi) as e:
        te.cevir({"a": 1, "b": 2}, "hf_models", [], keys, META, [])
    msg = str(e.value)
    assert "inside <root>" in msg and "(endpoint hf_models)" in msg and "'x'" in msg


def test_collision_below_the_root_names_the_path():
    keys = {"a": "x", "b": "x"}
    with pytest.raises(te.AdCakismasi) as e:
        te.cevir({"a": 1, "b": 2}, "hf_models", ["ozet", "alt"], keys, META, [])
    assert "inside ozet/alt" in str(e.value)


@pytest.fixture
def oz_test(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tempfile, "mkdtemp", lambda **k: str(tmp_path))

    def calistir():
        kod = te.oz_test(KOK / "ai-arz-serisi.ndjson")
        return kod, capsys.readouterr().out.splitlines()
    return calistir


def kontrol_satirlari(satirlar):
    return [s for s in satirlar if s.startswith("  [")]


def test_self_test_labels_every_passing_check_pass_and_counts_them(oz_test):
    kod, satirlar = oz_test()
    kontroller = kontrol_satirlari(satirlar)
    assert kod == 0 and kontroller
    assert all(s.startswith("  [PASS] ") for s in kontroller)
    assert satirlar[-1] == "SELF-TEST RESULT: %d passed / 0 failed" % len(kontroller)


def test_self_test_prints_details_only_when_a_check_has_them(oz_test):
    _, satirlar = oz_test()
    ilk = next(s for s in satirlar if "map loads" in s)
    assert ilk.endswith("— %d keys" % len(te.harita_yukle()[1]))
    olculemedi = next(s for s in satirlar if "`olculemedi` maps to `unmeasurable`" in s)
    assert "—" not in olculemedi


def _bozuk_harita(monkeypatch, degistir):
    gercek = te.harita_yukle

    def harita_yukle(*a, **k):
        meta, keys = gercek(*a, **k)
        keys = dict(keys)
        degistir(keys)
        return meta, keys
    monkeypatch.setattr(te, "harita_yukle", harita_yukle)


@pytest.mark.parametrize("ad", ["resource count", "kaynak_sayısı"])
def test_self_test_fails_an_english_name_with_a_space_or_a_turkish_letter(oz_test, monkeypatch, ad):
    _bozuk_harita(monkeypatch, lambda k: k.__setitem__("kaynak_sayisi", ad))
    kod, satirlar = oz_test()
    assert kod == 1
    assert any(s.startswith("  [FAIL] English names contain no Turkish characters or spaces") and ad in s
               for s in satirlar)


def test_self_test_fails_when_package_children_are_not_mapped(oz_test, monkeypatch):
    _bozuk_harita(monkeypatch, lambda k: k.__setitem__("toplam_30g", "total_30d"))
    kod, satirlar = oz_test()
    assert kod == 1
    assert any(s.startswith("  [FAIL] package identifiers pass through, their children still map")
               for s in satirlar)
