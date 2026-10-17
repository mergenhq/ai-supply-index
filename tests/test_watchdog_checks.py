"""Further checks on freshness_watchdog.py: thresholds at their documented values, boundaries,
rounding, message text and output format. Clock fixed at SIMDI; files under tmp_path."""
import json
import os
from datetime import timedelta

import pytest

import freshness_watchdog as w
from conftest import SIMDI, sabit_datetime

YESIL, SARI, KIRMIZI = 0, 1, 2


def ts(gun=0.0, saat=0.0):
    return (SIMDI - timedelta(days=gun, hours=saat)).isoformat(timespec="seconds")


def kosu(zaman, ozetler):
    return [json.dumps({"zaman_utc": zaman, "uc": uc, "ozet": o, "durum": "OK"}, ensure_ascii=False)
            for uc, o in ozetler.items()]


def seri(tmp_path, satirlar):
    yol = tmp_path / "seri.ndjson"
    yol.write_text("".join(s + "\n" for s in satirlar), encoding="utf-8")
    t = (SIMDI - timedelta(days=1)).timestamp()
    os.utime(yol, (t, t))
    return yol


def buyuyen(son_gun=1.0):
    return (kosu(ts(son_gun + 14), w._kaydir(w._SAGLAM, -20)) + kosu(ts(son_gun + 7), w._kaydir(w._SAGLAM, -10))
            + kosu(ts(son_gun), w._SAGLAM))


def uc_degistir(satirlar, uc):
    return [s for s in satirlar if '"uc": "%s"' % uc not in s]


# ── thresholds at their documented values ───────────────────────────────────
@pytest.mark.parametrize("gun,beklenen", [(7.9, YESIL), (8.5, SARI), (13.9, SARI), (14.5, KIRMIZI)])
def test_staleness_verdict_at_absolute_ages(tmp_path, gun, beklenen):
    kod, r = w.denetle(seri(tmp_path, kosu(ts(gun), w._SAGLAM)), SIMDI)
    assert kod == beklenen, r["findings"]


def test_frozen_needs_three_identical_runs_over_at_least_ten_days(tmp_path):
    def sabit_seri(gunler):
        s = []
        for i, g in enumerate(gunler):
            o = dict(w._kaydir(w._SAGLAM, 10 * i), sherlock_contests={"yarisma_sayisi": 301})
            s += kosu(ts(g), o)
        return s
    assert w.denetle(seri(tmp_path, sabit_seri([10.5, 5, 0.5])), SIMDI)[0] == SARI
    assert w.denetle(seri(tmp_path, sabit_seri([9.5, 5, 0.5])), SIMDI)[0] == YESIL
    assert w.denetle(seri(tmp_path, sabit_seri([20, 0.5])), SIMDI)[0] == YESIL


def test_frozen_message_names_the_derivation(tmp_path):
    s = kosu(ts(15), w._SAGLAM) + kosu(ts(8), w._SAGLAM) + kosu(ts(1), w._SAGLAM)
    _, r = w.denetle(seri(tmp_path, s), SIMDI)
    b = next(x for x in r["findings"] if "FROZEN" in x)
    assert "thresholds=3 runs & 10 days (derived from 28 runs, 2026-09-28)" in b


def test_streak_counts_only_values_equal_to_the_newest(tmp_path):
    s = uc_degistir(buyuyen(), "sherlock_contests")
    for g, v in ((22, 301), (15, 301), (8, 301), (1, 302)):
        s += kosu(ts(g), {"sherlock_contests": {"yarisma_sayisi": v}})
    kod, r = w.denetle(seri(tmp_path, s), SIMDI)
    assert r["consecutive_identical"]["sherlock_contests"] == 1 and kod == YESIL


def test_unparseable_newest_stamp_with_parseable_older_stamps_does_not_crash(tmp_path):
    s = kosu(ts(15), w._SAGLAM) + kosu(ts(8), w._SAGLAM) + kosu("zz-bozuk", w._SAGLAM)
    kod, r = w.denetle(seri(tmp_path, s), SIMDI)
    assert kod == KIRMIZI and not any("FROZEN" in b for b in r["findings"])


@pytest.mark.parametrize("gun,uyari", [(89.5, False), (90, False), (90.5, True)])
def test_stale_source_warns_only_past_90_days(tmp_path, gun, uyari):
    o = dict(w._SAGLAM, sherlock_contests={"yarisma_sayisi": 301, "en_yeni_baslangic_utc": ts(gun)})
    _, r = w.denetle(seri(tmp_path, kosu(ts(1), o)), SIMDI)
    assert any("STALE-SOURCE: sherlock_contests" in b for b in r["findings"]) == uyari


# ── one-run drop ────────────────────────────────────────────────────────────
def drop_seri(eski, yeni):
    s = uc_degistir(buyuyen(), "apify_store")
    return s + kosu(ts(8), {"apify_store": {"magaza_toplam_aktor": eski}}) \
             + kosu(ts(1), {"apify_store": {"magaza_toplam_aktor": yeni}})


@pytest.mark.parametrize("eski,yeni,dusus", [(100, 50, False), (100, 49, True), (1, 0.4, True), (0, -1, False)])
def test_drop_is_a_fall_of_more_than_half_from_a_positive_value(tmp_path, eski, yeni, dusus):
    _, r = w.denetle(seri(tmp_path, drop_seri(eski, yeni)), SIMDI)
    assert any("DROP: apify_store" in b for b in r["findings"]) == dusus


def test_drop_message_states_the_threshold(tmp_path):
    _, r = w.denetle(seri(tmp_path, drop_seri(100, 10)), SIMDI)
    assert any(b.endswith("fell from 100 to 10 (more than 50 % in one run)") for b in r["findings"])


# ── report values ───────────────────────────────────────────────────────────
def test_ages_are_rounded_to_three_decimals(tmp_path):
    yol = seri(tmp_path, kosu(ts(1, saat=1.5), w._SAGLAM))
    t = (SIMDI - timedelta(hours=7)).timestamp()
    os.utime(yol, (t, t))
    _, r = w.denetle(yol, SIMDI)
    assert r["record_age_days"] == 1.062 and r["file_mtime_age_days"] == 0.292


@pytest.mark.parametrize("yer", ["ozet", "paket"])
def test_unmeasurable_reason_is_cut_to_200_characters(tmp_path, yer):
    neden = "x" * 199 + "YZ"
    if yer == "ozet":
        o = dict(w._SAGLAM, hf_models=dict(w._SAGLAM["hf_models"], olculemedi=neden))
    else:
        o = dict(w._SAGLAM, npm_downloads={"pkg": {"toplam_30g": 5}, "b": {"olculemedi": neden}})
    _, r = w.denetle(seri(tmp_path, kosu(ts(1), o)), SIMDI)
    b = next(x for x in r["findings"] if "UNMEASURABLE" in x)
    assert b.endswith("x" * 199 + "Y")


def test_ledger_creates_missing_parent_folders(tmp_path):
    d = tmp_path / "a" / "b" / "alarm.ndjson"
    w.deftere_yaz(d, {"measured_utc": "t", "severity": "RED", "findings": ["RED x"]}, 2)
    assert json.loads(d.read_text(encoding="utf-8"))["sev"] == "CRITICAL"


# ── command line ────────────────────────────────────────────────────────────
def calistir(monkeypatch, argv):
    monkeypatch.setattr(w, "datetime", sabit_datetime(SIMDI))
    monkeypatch.setattr("sys.argv", ["freshness_watchdog.py"] + argv)
    return w.main()


def test_json_output_keeps_non_ascii_text_and_indents_by_one_space(tmp_path, monkeypatch, capsys):
    o = dict(w._SAGLAM, hf_models=dict(w._SAGLAM["hf_models"], olculemedi="ölçülemedi"))
    yol = seri(tmp_path, kosu(ts(1), o))
    assert calistir(monkeypatch, ["--series", str(yol), "--previous", "", "--json"]) == 2
    out = capsys.readouterr().out
    assert "ölçülemedi" in out and "—" in out
    assert out.startswith('{\n "series": ')


def test_self_test_labels_every_case_pass(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(w.tempfile, "mkdtemp", lambda **k: str(tmp_path))
    assert calistir(monkeypatch, ["--self-test"]) == 0
    satirlar = [s for s in capsys.readouterr().out.splitlines() if s.startswith("  [")]
    assert len(satirlar) == 10 and all(s.startswith("  [PASS] ") for s in satirlar)
