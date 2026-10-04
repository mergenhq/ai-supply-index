"""Tests for freshness_watchdog.py — clock fixed at SIMDI, series files under tmp_path."""
import json
import os
from datetime import timedelta

import pytest

import freshness_watchdog as w
from conftest import SIMDI, sabit_datetime

YESIL, SARI, KIRMIZI = 0, 1, 2


def ts(gun=0.0, saat=0.0):
    return (SIMDI - timedelta(days=gun, hours=saat)).isoformat(timespec="seconds")


def satir(zaman, uc, ozet, durum="OK"):
    return json.dumps({"zaman_utc": zaman, "surum": "0.2", "uc": uc, "ozet": ozet, "durum": durum},
                      ensure_ascii=False)


def kosu(zaman, ozetler, durumlar=None):
    durumlar = durumlar or {}
    return [satir(zaman, uc, o, durumlar.get(uc, "OK")) for uc, o in ozetler.items()]


def seri(tmp_path, satirlar, ad="seri.ndjson"):
    yol = tmp_path / ad
    yol.write_text("".join(s + "\n" for s in satirlar), encoding="utf-8")
    # pin the file mtime too, so file_mtime_age_days is deterministic
    t = (SIMDI - timedelta(days=1)).timestamp()
    os.utime(yol, (t, t))
    return yol


def saglikli(tmp_path, son_gun=1.0, extra=None):
    """Three weekly runs with growing counters, newest `son_gun` days ago."""
    s = (kosu(ts(son_gun + 14), w._kaydir(w._SAGLAM, -20))
         + kosu(ts(son_gun + 7), w._kaydir(w._SAGLAM, -10))
         + kosu(ts(son_gun), w._SAGLAM))
    return seri(tmp_path, s + (extra or []))


# ── pure helpers ────────────────────────────────────────────────────────────
class TestTopla:
    def test_sums_nested_field(self):
        assert w._topla({"a": {"n": 2}, "b": {"n": 3.5}}, "n") == 5.5

    def test_ignores_non_numeric_and_non_dict(self):
        assert w._topla({"a": {"n": "7"}, "b": 4, "c": {"n": 1}}, "n") == 1

    @pytest.mark.parametrize("ozet", [None, [], "x", 3, {}, {"a": {}}, {"a": {"hata": "x"}}])
    def test_none_when_nothing_found(self, ozet):
        assert w._topla(ozet, "n") is None

    def test_zero_is_kept_not_none(self):
        assert w._topla({"a": {"n": 0}}, "n") == 0


class TestDuz:
    def test_reads_field(self):
        assert w._duz({"k": 5}, "k") == 5

    @pytest.mark.parametrize("ozet", [None, [1], "k", 0])
    def test_non_dict_is_none(self, ozet):
        assert w._duz(ozet, "k") is None

    def test_missing_field_is_none(self):
        assert w._duz({"x": 1}, "k") is None


def test_every_carrier_reads_the_healthy_fixture():
    for uc, cikar in w.TASIYICILAR.items():
        assert cikar(w._SAGLAM[uc]) not in (None, 0), uc
    assert len(w.TASIYICILAR) == w.KAYITLI_UC


class TestYasGun:
    def test_z_suffix(self):
        assert w._yas_gun("2026-08-17T15:00:00Z", SIMDI) == pytest.approx(1.0)

    def test_offset(self):
        assert w._yas_gun("2026-08-18T17:00:00+02:00", SIMDI) == pytest.approx(0.0)

    def test_naive_is_treated_as_utc(self):
        assert w._yas_gun("2026-08-11T15:00:00", SIMDI) == pytest.approx(7.0)

    def test_future_is_negative(self):
        assert w._yas_gun("2026-08-19T15:00:00+00:00", SIMDI) == pytest.approx(-1.0)

    @pytest.mark.parametrize("bozuk", ["", "dun", "2026-13-01T00:00:00", None, 123])
    def test_unparseable_is_none(self, bozuk):
        assert w._yas_gun(bozuk, SIMDI) is None


class TestKayitlar:
    def test_missing_file(self, tmp_path):
        assert w.kayitlar(tmp_path / "yok.ndjson") == []

    def test_empty_file(self, tmp_path):
        p = tmp_path / "s.ndjson"
        p.write_text("", encoding="utf-8")
        assert w.kayitlar(p) == []

    def test_skips_blank_and_invalid_json(self, tmp_path):
        p = tmp_path / "s.ndjson"
        p.write_text('{"a": 1}\n\n   \n{bozuk\n{"b": 2}\n', encoding="utf-8")
        assert w.kayitlar(p) == [{"a": 1}, {"b": 2}]

    def test_returns_non_object_json_values_verbatim(self, tmp_path):
        p = tmp_path / "s.ndjson"
        p.write_text('42\n"x"\n[1]\nnull\n', encoding="utf-8")
        assert w.kayitlar(p) == [42, "x", [1], None]


# ── denetle(): verdicts ─────────────────────────────────────────────────────
class TestDenetle:
    def test_healthy_is_green(self, tmp_path):
        kod, r = w.denetle(saglikli(tmp_path), SIMDI)
        assert kod == YESIL and r["severity"] == "GREEN"
        assert r["record_count"] == 30 and r["run_count"] == 3
        assert r["last_run_endpoint_count"] == 10
        assert r["record_age_days"] == pytest.approx(1.0)
        assert r["file_mtime_age_days"] == pytest.approx(1.0)
        assert r["findings"][-1].startswith("GREEN")
        assert "10/10 endpoints populated" in r["findings"][-1]
        assert set(r["last_run_carriers"]) == set(w.TASIYICILAR)

    def test_default_now_uses_wall_clock_but_is_injectable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w, "datetime", sabit_datetime(SIMDI))
        kod, r = w.denetle(saglikli(tmp_path))
        assert kod == YESIL
        assert r["measured_utc"] == SIMDI.isoformat(timespec="seconds")

    def test_missing_series_is_red(self, tmp_path):
        kod, r = w.denetle(tmp_path / "yok.ndjson", SIMDI)
        assert kod == KIRMIZI and r["record_count"] == 0
        assert "EMPTY or MISSING" in r["findings"][0]

    def test_empty_series_is_red(self, tmp_path):
        kod, r = w.denetle(seri(tmp_path, []), SIMDI)
        assert kod == KIRMIZI

    def test_only_garbage_lines_is_red(self, tmp_path):
        kod, _ = w.denetle(seri(tmp_path, ["{bozuk", "not json"]), SIMDI)
        assert kod == KIRMIZI

    def test_invalid_json_line_is_ignored(self, tmp_path):
        kod, r = w.denetle(saglikli(tmp_path, extra=["{yarim satir"]), SIMDI)
        assert kod == YESIL and r["record_count"] == 30

    # staleness thresholds are strict ">" comparisons
    @pytest.mark.parametrize("gun,beklenen", [
        (0.0, YESIL),
        (w.TAZELIK_SARI_GUN, YESIL),
        (w.TAZELIK_SARI_GUN + 1 / 24, SARI),
        (w.TAZELIK_KIRMIZI_GUN, SARI),
        (w.TAZELIK_KIRMIZI_GUN + 1 / 24, KIRMIZI),
        (30, KIRMIZI),
    ])
    def test_staleness_boundaries(self, tmp_path, gun, beklenen):
        kod, r = w.denetle(seri(tmp_path, kosu(ts(gun), w._SAGLAM)), SIMDI)
        assert kod == beklenen, r["findings"]

    def test_stale_message(self, tmp_path):
        _, r = w.denetle(seri(tmp_path, kosu(ts(20), w._SAGLAM)), SIMDI)
        assert any("STALE" in b for b in r["findings"])

    def test_future_stamp_is_not_stale(self, tmp_path):
        kod, _ = w.denetle(seri(tmp_path, kosu(ts(-2), w._SAGLAM)), SIMDI)
        assert kod == YESIL

    def test_unparseable_last_stamp_is_red(self, tmp_path):
        kod, r = w.denetle(seri(tmp_path, kosu("bozuk-damga", w._SAGLAM)), SIMDI)
        assert kod == KIRMIZI and r["record_age_days"] is None
        assert any("UNREADABLE" in b for b in r["findings"])

    def test_rows_without_stamp_are_red(self, tmp_path):
        s = [json.dumps({"uc": uc, "ozet": o, "durum": "OK"}) for uc, o in w._SAGLAM.items()]
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == KIRMIZI and r["last_record_utc"] is None and r["run_count"] == 0

    def test_record_stamp_wins_over_file_mtime(self, tmp_path):
        yol = seri(tmp_path, kosu(ts(20), w._SAGLAM))
        t = SIMDI.timestamp()
        os.utime(yol, (t, t))                    # touched just now, content is 20 days old
        kod, r = w.denetle(yol, SIMDI)
        assert kod == KIRMIZI
        assert r["file_mtime_age_days"] == pytest.approx(0.0)

    def test_last_run_is_the_latest_stamp_regardless_of_file_order(self, tmp_path):
        eski = kosu(ts(8), w._kaydir(w._SAGLAM, -10))
        yeni = kosu(ts(1), w._SAGLAM)
        _, r = w.denetle(seri(tmp_path, yeni + eski), SIMDI)
        assert r["last_record_utc"] == ts(1)

    def test_missing_endpoint_is_red(self, tmp_path):
        eksik = {k: v for k, v in w._SAGLAM.items() if k not in ("hf_models", "apify_store")}
        kod, r = w.denetle(seri(tmp_path, kosu(ts(1), eksik)), SIMDI)
        assert kod == KIRMIZI
        b = [x for x in r["findings"] if "MISSING-ENDPOINT" in x][0]
        assert "8/10" in b and "dropped=apify_store,hf_models" in b

    def test_extra_unknown_endpoint_is_tolerated(self, tmp_path):
        extra = [satir(ts(1), "code4rena_audits", {"yarisma_sayisi": 475})]
        kod, r = w.denetle(saglikli(tmp_path, extra=extra), SIMDI)
        assert kod == YESIL
        assert "code4rena_audits" not in r["last_run_carriers"]

    @pytest.mark.parametrize("durum", ["HTTP-HATA", "HATA", "HATA-ICERIDE"])
    def test_endpoint_error_status_is_red(self, tmp_path, durum):
        kod, r = w.denetle(seri(tmp_path, kosu(ts(1), w._SAGLAM, {"apify_store": durum})), SIMDI)
        assert kod == KIRMIZI
        assert any("ENDPOINT-ERROR: apify_store status=%s" % durum in b for b in r["findings"])

    def test_missing_status_field_is_not_an_error(self, tmp_path):
        s = [json.dumps({"zaman_utc": ts(1), "uc": uc, "ozet": o}) for uc, o in w._SAGLAM.items()]
        kod, _ = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == YESIL

    def test_silent_zero_is_red(self, tmp_path):
        o = dict(w._SAGLAM, sherlock_leaderboard={"arastirmaci_sayisi": 0})
        kod, r = w.denetle(seri(tmp_path, kosu(ts(1), o)), SIMDI)
        assert kod == KIRMIZI and r["last_run_carriers"]["sherlock_leaderboard"] == 0
        assert any("SILENT-ZERO: sherlock_leaderboard" in b for b in r["findings"])

    def test_silent_zero_in_nested_carrier(self, tmp_path):
        o = dict(w._SAGLAM, npm_downloads={"a": {"toplam_30g": 0}, "b": {"toplam_30g": 0}})
        kod, r = w.denetle(seri(tmp_path, kosu(ts(1), o)), SIMDI)
        assert kod == KIRMIZI
        assert any("SILENT-ZERO: npm_downloads" in b for b in r["findings"])

    @pytest.mark.parametrize("ozet", [{"resource_count": 5}, {}, None, "x", [1]])
    def test_silent_none_is_red(self, tmp_path, ozet):
        o = dict(w._SAGLAM, x402_discovery=ozet)
        kod, r = w.denetle(seri(tmp_path, kosu(ts(1), o)), SIMDI)
        assert kod == KIRMIZI
        assert any("SILENT-NONE: x402_discovery" in b for b in r["findings"])

    def test_row_without_ozet_is_silent_none(self, tmp_path):
        s = kosu(ts(1), {k: v for k, v in w._SAGLAM.items() if k != "hf_models"})
        s.append(json.dumps({"zaman_utc": ts(1), "uc": "hf_models", "durum": "HATA"}))
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == KIRMIZI
        assert any("SILENT-NONE: hf_models" in b for b in r["findings"])
        assert any("ENDPOINT-ERROR: hf_models" in b for b in r["findings"])

    def test_red_beats_yellow(self, tmp_path):
        o = dict(w._SAGLAM, hf_models={"model_sayisi": 0})
        kod, r = w.denetle(seri(tmp_path, kosu(ts(10), o)), SIMDI)
        assert kod == KIRMIZI
        assert any(b.startswith("RED") for b in r["findings"])
        assert any(b.startswith("YELLOW") for b in r["findings"])
        assert r["findings"].index(next(b for b in r["findings"] if b.startswith("RED"))) == 0


# ── frozen series ───────────────────────────────────────────────────────────
class TestDonmus:
    def test_three_identical_runs_over_14_days_is_yellow(self, tmp_path):
        s = kosu(ts(15), w._SAGLAM) + kosu(ts(8), w._SAGLAM) + kosu(ts(1), w._SAGLAM)
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == SARI
        assert r["consecutive_identical"]["hf_models"] == 3
        assert sum("FROZEN" in b for b in r["findings"]) == 10

    def test_spread_exactly_at_threshold_is_frozen(self, tmp_path):
        s = (kosu(ts(1 + w.DONMUS_MIN_YAYILIM_GUN), w._SAGLAM)
             + kosu(ts(5), w._SAGLAM) + kosu(ts(1), w._SAGLAM))
        kod, _ = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == SARI

    def test_spread_just_below_threshold_is_green(self, tmp_path):
        s = (kosu(ts(1 + w.DONMUS_MIN_YAYILIM_GUN, saat=-1), w._SAGLAM)
             + kosu(ts(5), w._SAGLAM) + kosu(ts(1), w._SAGLAM))
        kod, _ = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == YESIL

    def test_same_day_repeats_are_not_frozen(self, tmp_path):
        s = (kosu(ts(saat=8), w._SAGLAM) + kosu(ts(saat=7), w._SAGLAM)
             + kosu(ts(saat=1), w._SAGLAM))
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == YESIL and r["consecutive_identical"]["hf_models"] == 3

    def test_two_identical_runs_below_count_threshold(self, tmp_path):
        s = kosu(ts(15), w._SAGLAM) + kosu(ts(1), w._SAGLAM)
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == YESIL and r["consecutive_identical"]["hf_models"] == 2

    def test_only_the_trailing_streak_counts(self, tmp_path):
        s = (kosu(ts(22), w._SAGLAM) + kosu(ts(15), w._kaydir(w._SAGLAM, 1))
             + kosu(ts(8), w._SAGLAM) + kosu(ts(1), w._SAGLAM))
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == YESIL and r["consecutive_identical"]["x402_discovery"] == 2

    def test_single_run_has_no_streak_entry(self, tmp_path):
        _, r = w.denetle(seri(tmp_path, kosu(ts(1), w._SAGLAM)), SIMDI)
        assert r["consecutive_identical"] == {}

    def test_none_values_never_form_a_streak(self, tmp_path):
        o = dict(w._SAGLAM, hf_models={})
        s = kosu(ts(15), o) + kosu(ts(8), o) + kosu(ts(1), o)
        _, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert r["consecutive_identical"]["hf_models"] == 1

    def test_one_frozen_endpoint_only(self, tmp_path):
        s = (kosu(ts(15), w._kaydir(w._SAGLAM, -20)) + kosu(ts(8), w._kaydir(w._SAGLAM, -10))
             + kosu(ts(1), w._SAGLAM))
        sabit = {"sherlock_contests": {"yarisma_sayisi": 301}}
        s = [x for x in s if '"sherlock_contests"' not in x]
        s += kosu(ts(15), sabit) + kosu(ts(8), sabit) + kosu(ts(1), sabit)
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == SARI
        assert [b for b in r["findings"] if "FROZEN" in b][0].startswith("YELLOW FROZEN: sherlock_contests")


# ── ledger ──────────────────────────────────────────────────────────────────
class TestDeftereYaz:
    def rapor(self, sev="RED", bulgular=None):
        return {"measured_utc": "2026-08-18T15:00:00+00:00", "severity": sev,
                "findings": bulgular or ["RED x"], "record_age_days": 1.0,
                "last_run_endpoint_count": 9, "last_run_carriers": {"hf_models": 0}}

    def test_green_writes_nothing(self, tmp_path):
        d = tmp_path / "logs" / "alarm.ndjson"
        w.deftere_yaz(d, self.rapor("GREEN"), 0)
        assert not d.exists() and not d.parent.exists()

    @pytest.mark.parametrize("kod,sev,sevlik", [(2, "RED", "CRITICAL"), (1, "YELLOW", "WARN")])
    def test_alarm_line(self, tmp_path, kod, sev, sevlik):
        d = tmp_path / "logs" / "alarm.ndjson"
        w.deftere_yaz(d, self.rapor(sev), kod)
        k = json.loads(d.read_text(encoding="utf-8"))
        assert k["sev"] == sevlik and k["dedup_key"] == "ai-arz|tazelik|%s" % sev
        assert k["sinif"] == "AI_ARZ_%s" % sev and k["ts"] == "2026-08-18T15:00:00+00:00"
        assert k["meta"] == {"record_age_days": 1.0, "last_run_endpoint_count": 9,
                             "carriers": {"hf_models": 0}}

    def test_appends_and_truncates(self, tmp_path):
        d = tmp_path / "alarm.ndjson"
        w.deftere_yaz(d, self.rapor(bulgular=["RED " + "ç" * 1000]), 2)
        w.deftere_yaz(d, self.rapor(), 2)
        satirlar = d.read_text(encoding="utf-8").splitlines()
        assert len(satirlar) == 2
        assert len(json.loads(satirlar[0])["msg"]) == 600
        assert "ç" in satirlar[0]                     # ensure_ascii=False


# ── CLI ─────────────────────────────────────────────────────────────────────
class TestMain:
    def calistir(self, monkeypatch, argv):
        monkeypatch.setattr(w, "datetime", sabit_datetime(SIMDI))
        monkeypatch.setattr("sys.argv", ["freshness_watchdog.py"] + argv)
        return w.main()

    def test_text_output_green(self, tmp_path, monkeypatch, capsys):
        kod = self.calistir(monkeypatch, ["--series", str(saglikli(tmp_path))])
        out = capsys.readouterr().out
        assert kod == 0 and "FRESHNESS WATCHDOG — GREEN" in out and "age 1.00 days" in out

    def test_json_output(self, tmp_path, monkeypatch, capsys):
        kod = self.calistir(monkeypatch, ["--series", str(tmp_path / "yok.ndjson"), "--json"])
        r = json.loads(capsys.readouterr().out)
        assert kod == 2 and r["severity"] == "RED"

    def test_ledger_written_only_on_alarm(self, tmp_path, monkeypatch, capsys):
        d = tmp_path / "alarm.ndjson"
        assert self.calistir(monkeypatch, ["--series", str(saglikli(tmp_path)), "--ledger", str(d)]) == 0
        assert not d.exists()
        assert self.calistir(monkeypatch, ["--series", str(tmp_path / "yok"), "--ledger", str(d)]) == 2
        assert json.loads(d.read_text(encoding="utf-8"))["sev"] == "CRITICAL"

    def test_self_test_passes(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(w.tempfile, "mkdtemp", lambda **k: str(tmp_path))
        assert self.calistir(monkeypatch, ["--self-test"]) == 0
        assert "10 passed / 0 failed" in capsys.readouterr().out


# ── regressions for the two verified bugs ───────────────────────────────────
class TestH1NonObjectRows:
    """H1: a line that is valid JSON but not an object (e.g. a bare `42`) crashed denetle()
    with AttributeError. Expected: skipped, counted in the report, no crash."""

    @pytest.mark.parametrize("bozuk", ["42", '"metin"', "[1, 2]", "null", "true"])
    def test_non_object_row_is_skipped_and_counted(self, tmp_path, bozuk):
        kod, r = w.denetle(saglikli(tmp_path, extra=[bozuk]), SIMDI)
        assert kod == YESIL
        assert r["record_count"] == 30
        assert r["skipped_non_object_rows"] == 1
        assert any("1 non-object row" in b for b in r["findings"])

    def test_several_rows_mid_series(self, tmp_path):
        s = (kosu(ts(15), w._kaydir(w._SAGLAM, -20)) + ["42"]
             + kosu(ts(8), w._kaydir(w._SAGLAM, -10)) + ["[]", "null"] + kosu(ts(1), w._SAGLAM))
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == YESIL and r["skipped_non_object_rows"] == 3

    def test_skip_does_not_mask_a_real_alarm(self, tmp_path):
        o = dict(w._SAGLAM, hf_models={"model_sayisi": 0})
        kod, r = w.denetle(seri(tmp_path, kosu(ts(1), o) + ["42"]), SIMDI)
        assert kod == KIRMIZI and r["skipped_non_object_rows"] == 1

    def test_only_non_object_rows_is_red_empty(self, tmp_path):
        kod, r = w.denetle(seri(tmp_path, ["42", "[1]"]), SIMDI)
        assert kod == KIRMIZI
        assert r["record_count"] == 0 and r["skipped_non_object_rows"] == 2

    def test_clean_series_reports_zero_skipped(self, tmp_path):
        kod, r = w.denetle(saglikli(tmp_path), SIMDI)
        assert r["skipped_non_object_rows"] == 0
        assert not any("non-object" in b for b in r["findings"])


class TestH2DistinctEndpoints:
    """H2: the last run's endpoint count was len(records), so a dropped endpoint hidden by a
    duplicate of another one read as 10/10 GREEN. Expected: distinct endpoint names count."""

    def test_dropped_endpoint_masked_by_duplicate_is_red(self, tmp_path):
        o = {k: v for k, v in w._SAGLAM.items() if k != "hf_models"}
        s = kosu(ts(1), o) + kosu(ts(1), {"github_repos": w._SAGLAM["github_repos"]})
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == KIRMIZI
        assert r["last_run_endpoint_count"] == 9
        b = [x for x in r["findings"] if "MISSING-ENDPOINT" in x]
        assert b and "9/10" in b[0] and "dropped=hf_models" in b[0]

    def test_dropped_endpoint_masked_by_untracked_endpoint_is_red(self, tmp_path):
        # the real collector writes 11 rows per run (code4rena_audits is not a tracked carrier)
        o = {k: v for k, v in w._SAGLAM.items() if k != "apify_store"}
        s = kosu(ts(1), o) + [satir(ts(1), "code4rena_audits", {"yarisma_sayisi": 475})]
        kod, r = w.denetle(seri(tmp_path, s), SIMDI)
        assert kod == KIRMIZI
        assert any("dropped=apify_store" in b for b in r["findings"])

    def test_duplicates_with_all_endpoints_present_stay_green(self, tmp_path):
        extra = kosu(ts(1), {"github_repos": w._SAGLAM["github_repos"]})
        kod, r = w.denetle(saglikli(tmp_path, extra=extra), SIMDI)
        assert kod == YESIL and r["last_run_endpoint_count"] == 10

    def test_real_shaped_run_with_eleven_rows_is_10_of_10(self, tmp_path):
        extra = [satir(ts(1), "code4rena_audits", {"yarisma_sayisi": 475})]
        kod, r = w.denetle(saglikli(tmp_path, extra=extra), SIMDI)
        assert kod == YESIL and r["last_run_endpoint_count"] == 10


class TestStaleSource:
    """An open-window endpoint whose newest entry started long ago is flagged YELLOW."""
    def seri_ile(self, tmp_path, baslangic):
        son = dict(w._SAGLAM)
        son["sherlock_contests"] = dict(son["sherlock_contests"], en_yeni_baslangic_utc=baslangic)
        s = (kosu(ts(15), w._kaydir(w._SAGLAM, -20)) + kosu(ts(8), w._kaydir(w._SAGLAM, -10))
             + kosu(ts(1), son))
        return seri(tmp_path, s)

    def test_old_newest_entry_is_yellow(self, tmp_path):
        kod, r = w.denetle(self.seri_ile(tmp_path, ts(w.KAYNAK_ESKI_GUN + 1)), SIMDI)
        assert kod == SARI
        assert any("STALE-SOURCE: sherlock_contests" in b for b in r["findings"])

    def test_recent_newest_entry_is_green(self, tmp_path):
        kod, r = w.denetle(self.seri_ile(tmp_path, ts(w.KAYNAK_ESKI_GUN - 1)), SIMDI)
        assert kod == YESIL, r["findings"]

    @pytest.mark.parametrize("deger", [None, "bozuk"])
    def test_missing_or_unreadable_field_is_ignored(self, tmp_path, deger):
        kod, r = w.denetle(self.seri_ile(tmp_path, deger), SIMDI)
        assert kod == YESIL, r["findings"]


class TestAppendOnly:
    """The series must begin with the previous published snapshot, byte for byte."""
    def test_series_extending_the_snapshot_is_green(self, tmp_path):
        yol = saglikli(tmp_path)
        onceki = tmp_path / "onceki.ndjson"
        onceki.write_text("".join(yol.read_text(encoding="utf-8").splitlines(True)[:10]), encoding="utf-8")
        kod, r = w.denetle(yol, SIMDI, onceki=onceki)
        assert kod == YESIL, r["findings"]

    def test_reordered_rows_are_red(self, tmp_path):
        yol = saglikli(tmp_path)
        satirlar = yol.read_text(encoding="utf-8").splitlines(True)
        onceki = tmp_path / "onceki.ndjson"
        onceki.write_text("".join(satirlar[:10]), encoding="utf-8")
        satirlar[0], satirlar[1] = satirlar[1], satirlar[0]
        yol.write_text("".join(satirlar), encoding="utf-8")
        kod, r = w.denetle(yol, SIMDI, onceki=onceki)
        assert kod == KIRMIZI
        assert any("NOT-APPEND-ONLY" in b and "onceki.ndjson" in b for b in r["findings"])

    def test_missing_snapshot_is_ignored(self, tmp_path):
        kod, r = w.denetle(saglikli(tmp_path), SIMDI, onceki=tmp_path / "yok.ndjson")
        assert kod == YESIL, r["findings"]

    def test_cli_uses_newest_archive_snapshot_by_default(self, tmp_path, monkeypatch, capsys):
        yol = saglikli(tmp_path)
        (tmp_path / "archive").mkdir()
        (tmp_path / "archive" / "ai-arz-serisi-20260101T000000Z.ndjson").write_text("eski\n", encoding="utf-8")
        (tmp_path / "archive" / "ai-arz-serisi-20260801T000000Z.ndjson").write_text("yeni\n", encoding="utf-8")
        monkeypatch.setattr(w, "datetime", sabit_datetime(SIMDI))
        monkeypatch.setattr("sys.argv", ["freshness_watchdog.py", "--series", str(yol)])
        assert w.main() == KIRMIZI
        assert "ai-arz-serisi-20260801T000000Z.ndjson" in capsys.readouterr().out

    def test_cli_previous_empty_disables_the_check(self, tmp_path, monkeypatch, capsys):
        yol = saglikli(tmp_path)
        (tmp_path / "archive").mkdir()
        (tmp_path / "archive" / "ai-arz-serisi-20260801T000000Z.ndjson").write_text("x\n", encoding="utf-8")
        monkeypatch.setattr(w, "datetime", sabit_datetime(SIMDI))
        monkeypatch.setattr("sys.argv", ["freshness_watchdog.py", "--series", str(yol), "--previous", ""])
        assert w.main() == YESIL
