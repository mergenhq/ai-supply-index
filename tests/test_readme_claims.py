"""Checks that statements in the README sections "Method", "Known limits" and "Using the series"
hold for the code and the published files. Each test quotes the statement it checks."""
import collections
import json
import statistics
from datetime import datetime

import collector as c
import freshness_watchdog as w
from conftest import KOK

README = (KOK / "README.md").read_text(encoding="utf-8")
SATIRLAR = [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()
            if x.strip()]
KOSULAR = collections.defaultdict(list)
for _r in SATIRLAR:
    KOSULAR[_r["zaman_utc"]].append(_r)
HARITA = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))
ESLEME = {k[0]: k[1] for g in HARITA["groups"] for k in g["keys"]}


def tarih(t):
    return datetime.fromisoformat(t)


def bolum(baslik):
    a = README.index(baslik)
    return README[a:README.index("\n## ", a + 1) if "\n## " in README[a + 1:] else len(README)]


# ── Method ──────────────────────────────────────────────────────────────────
def test_eleven_endpoints():
    """'**11 endpoints**, all public'"""
    assert "**11 endpoints**" in bolum("## Method")
    assert len(c.UCLAR) == 11 and len({u[0] for u in c.UCLAR}) == 11
    son = max(KOSULAR)
    assert {r["uc"] for r in KOSULAR[son]} == {u[0] for u in c.UCLAR}


def test_requests_carry_no_credentials(monkeypatch):
    """'no authentication, no account'"""
    gorulen = {}

    def urlopen(req, timeout):
        gorulen.update(req.header_items())
        raise OSError("stop")
    monkeypatch.setattr(c.urllib.request, "urlopen", urlopen)
    try:
        c.cek("https://ornek.test")
    except OSError:
        pass
    assert set(gorulen) == {"User-agent", "Accept"}


def test_complete_runs_take_70_to_190_seconds_with_a_median_near_100():
    """'One run takes about 70–190 seconds for all 11 endpoints (median ≈ 100 s up to 2026-09-28)'
    Checked on runs in which every endpoint row is OK."""
    sureler = [sum(x.get("saniye") or 0 for x in rs) for t, rs in KOSULAR.items()
               if t <= "2026-09-28T23:59:59" and len(rs) >= 10 and all(x.get("durum") == "OK" for x in rs)]
    assert sureler and 70 <= min(sureler) and max(sureler) <= 190
    assert 90 <= statistics.median(sureler) <= 110


def test_one_line_per_endpoint_per_run():
    """'Every run appends one line per endpoint'"""
    assert all(len(rs) == len({x["uc"] for x in rs}) for rs in KOSULAR.values())


def test_scheduled_runs_fall_on_mondays_and_thursdays_at_07_utc():
    """'Runs twice a week, Mondays and Thursdays 07:00 UTC'"""
    sonra = [tarih(t) for t in KOSULAR if t >= "2026-08-22"]
    yedi = [d for d in sonra if d.hour == 7]
    assert yedi and all(d.weekday() in (0, 3) and d.minute < 5 for d in yedi)
    gunler = {d.date() for d in yedi}
    d = min(gunler)
    while d <= max(gunler):
        if d.weekday() in (0, 3):
            assert d in gunler, d
        d = d.fromordinal(d.toordinal() + 1)


def test_set_up_runs_up_to_six_a_day():
    """'set-up runs of 2026-08-18 to 2026-08-21 (up to six a day)'"""
    gunluk = collections.Counter(tarih(t).date().isoformat() for t in KOSULAR if t < "2026-08-22")
    assert set(gunluk) <= {"2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"}
    assert max(gunluk.values()) == 6


def test_second_collector_runs_fall_between_2026_08_20_and_2026_09_14():
    """'from 2026-08-20 to 2026-09-14 a second collector ran at about 06:30 UTC'"""
    alti = [tarih(t) for t in KOSULAR if tarih(t).hour == 6]
    assert alti and all("2026-08-20" <= d.date().isoformat() <= "2026-09-14" for d in alti)
    assert {d.date().isoformat() for d in alti} >= {"2026-08-20", "2026-09-14"}


def test_collector_id_key_is_documented():
    """'carry its name in `toplayici` (`collector_id`)'"""
    assert ESLEME["toplayici"] == "collector_id"


def test_every_snapshot_has_a_stamp_next_to_it():
    """'that snapshot is stamped next to it (`archive/ai-arz-serisi-<UTC stamp>.ndjson.ots`)'"""
    anlik = sorted((KOK / "archive").glob("ai-arz-serisi-*.ndjson"))
    assert anlik and all(p.with_name(p.name + ".ots").exists() for p in anlik)


def test_each_snapshot_extends_the_previous_one_unchanged():
    """'Every publication since then extends the previous one unchanged'"""
    anlik = [p.read_bytes() for p in sorted((KOK / "archive").glob("ai-arz-serisi-*.ndjson"))]
    anlik.append((KOK / "ai-arz-serisi.ndjson").read_bytes())
    assert all(b.startswith(a) for a, b in zip(anlik, anlik[1:]))


# ── Known limits ────────────────────────────────────────────────────────────
def test_payload_size_field_is_documented():
    """'a `bayt` field records payload size'"""
    assert ESLEME["bayt"] == "bytes"
    assert all(isinstance(r["bayt"], int) for r in SATIRLAR if "bayt" in r)


def test_apify_and_hugging_face_samples():
    """'Apify: top 1,000 of 47,257 by popularity, of which about 835–870 per run carry a numeric
    user count ... Hugging Face: top 100.' — counts checked on the runs up to 2026-09-28."""
    ap = [r["ozet"] for r in SATIRLAR if r["uc"] == "apify_store" and r.get("durum") == "OK"
          and r["zaman_utc"] <= "2026-09-28T23:59:59"]
    assert all(o["sayfa"] == 10 for o in ap)
    assert 47257 in {o["magaza_toplam_aktor"] for o in ap}
    assert all(835 <= o["taranan"] <= 870 for o in ap)
    hf = [r["ozet"] for r in SATIRLAR if r["uc"] == "hf_models" and r.get("durum") == "OK"]
    assert all(o["model_sayisi"] == 100 for o in hf)
    assert any("limit=100" in str(k) for k in c.uc_hf_modeller.__code__.co_consts)


def test_series_starts_on_2026_08_18():
    """'The series starts on 2026-08-18.'"""
    assert min(KOSULAR).startswith("2026-08-18")


def test_watchdog_guards_all_eleven_endpoints():
    """'The watchdog guards all 11 of the 11 endpoints.'"""
    assert set(w.TASIYICILAR) == {u[0] for u in c.UCLAR} and w.KAYITLI_UC == 11


def test_frozen_thresholds_were_derived_from_the_runs_up_to_2026_09_28():
    """'The frozen thresholds and carriers were re-derived from the 28 runs up to 2026-09-28'"""
    assert len([t for t in KOSULAR if t <= "2026-09-28T23:59:59"]) == w.DONMUS_TURETME_KOSU == 28
    assert w.DONMUS_TURETME_TARIHI == "2026-09-28"


def test_hugging_face_and_defillama_carriers_are_summed_values_that_change_over_a_day():
    """'the Hugging Face and DeFiLlama category carriers are now the summed downloads and the summed
    30-day fees' — checked on OK runs that are at least a day apart."""
    assert w.TASIYICILAR["hf_models"]({"indirme_dagilimi": {"toplam": 5}}) == 5
    assert w.TASIYICILAR["defillama_fees_ai_agents"]({"ai_total30d": 7}) == 7
    for uc in ("hf_models", "defillama_fees_ai_agents"):
        v = [(tarih(r["zaman_utc"]), w.TASIYICILAR[uc](r["ozet"]))
             for r in SATIRLAR if r["uc"] == uc and r.get("durum") == "OK"]
        v = [x for x in v if x[1] is not None]
        for (ta, a), (tb, b) in zip(v, v[1:]):
            if (tb - ta).total_seconds() >= 86400:
                assert a != b, (uc, ta, tb)


def test_cantina_is_implemented_but_not_wired_in():
    """'`cantina_competitions` is implemented and measured but not yet wired in.'"""
    assert callable(c.uc_cantina_competitions)
    assert "cantina_competitions" not in {u[0] for u in c.UCLAR}
    assert not any(r["uc"] == "cantina_competitions" for r in SATIRLAR)


# ── Using the series ────────────────────────────────────────────────────────
def test_some_days_carry_more_than_one_run_and_some_rows_are_incomplete():
    """'Some days carry more than one run (see *Method*), and a row can be incomplete'"""
    gunluk = collections.Counter(tarih(t).date() for t in KOSULAR)
    assert max(gunluk.values()) > 1
    assert any(r.get("durum") != "OK" or "olculemedi" in (r.get("ozet") or {}) for r in SATIRLAR)


def test_weekly_example_is_linked_and_exists():
    """'[`examples/weekly_series.py`](examples/weekly_series.py)'"""
    assert "](examples/weekly_series.py)" in bolum("## Using the series")
    assert (KOK / "examples" / "weekly_series.py").exists()
