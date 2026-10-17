"""The measurements the watchdog's thresholds are derived from (comments in freshness_watchdog.py,
'series up to 2026-09-28') hold on the published series. Files are only read."""
import json
from datetime import datetime

import collector as c
import freshness_watchdog as w
from conftest import KOK

KAYNAK = (KOK / "freshness_watchdog.py").read_text(encoding="utf-8")
SATIRLAR = [r for r in (json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8")
                        .splitlines() if x.strip())
            if r["zaman_utc"] <= "2026-09-28T23:59:59"]


def kullanilir(r):
    o = r.get("ozet")
    return r.get("durum") == "OK" and isinstance(o, dict) and "olculemedi" not in o


def en_uzun_sabit_gun(uc, oku):
    """Longest stretch, in days, over which consecutive usable values of `uc` stayed identical."""
    v = [(datetime.fromisoformat(r["zaman_utc"]), oku(r["ozet"])) for r in SATIRLAR
         if r["uc"] == uc and kullanilir(r)]
    v = [x for x in v if x[1] is not None]
    en, bas = 0.0, 0
    for i in range(1, len(v) + 1):
        if i == len(v) or v[i][1] != v[bas][1]:
            en = max(en, (v[i - 1][0] - v[bas][0]).total_seconds() / 86400)
            bas = i
    return en


def test_derivation_uses_28_runs_over_41_days():
    """'RE-DERIVED [series up to 2026-09-28, 28 runs, 41 days]'"""
    damgalar = sorted({r["zaman_utc"] for r in SATIRLAR})
    assert len(damgalar) == 28 == w.DONMUS_TURETME_KOSU
    gun = (datetime.fromisoformat(damgalar[-1]) - datetime.fromisoformat(damgalar[0])).total_seconds() / 86400
    assert round(gun) == 41 and "28 runs, 41 days" in KAYNAK


def test_slow_counters_were_flat_for_the_stated_number_of_days():
    """'sherlock_leaderboard 25 days, sherlock_contests 41 days, the AI-agent protocol count 21 days,
    model_sayisi 41 days'"""
    assert "sherlock_leaderboard 25 days" in KAYNAK and "sherlock_contests 41 days" in KAYNAK
    assert round(en_uzun_sabit_gun("sherlock_leaderboard", w.TASIYICILAR["sherlock_leaderboard"])) == 25
    assert round(en_uzun_sabit_gun("sherlock_contests", w.TASIYICILAR["sherlock_contests"])) == 41
    assert round(en_uzun_sabit_gun("defillama_fees_ai_agents", lambda o: o.get("ai_agent_protokol_sayisi"))) == 21
    assert round(en_uzun_sabit_gun("hf_models", lambda o: o.get("model_sayisi"))) == 41


def test_frozen_rule_fires_on_the_slow_sherlock_counters():
    """'still fires on the Sherlock counters'"""
    for uc in ("sherlock_leaderboard", "sherlock_contests"):
        assert en_uzun_sabit_gun(uc, w.TASIYICILAR[uc]) >= w.DONMUS_MIN_YAYILIM_GUN


def tek_kosu_dususleri():
    out = []
    for uc, oku in w.TASIYICILAR.items():
        v = [(r["zaman_utc"], oku(r["ozet"]), c.hata_iceride(r["ozet"])) for r in SATIRLAR
             if r["uc"] == uc and kullanilir(r)]
        v = [x for x in v if x[1] is not None]
        for (_, a, ha), (t, b, hb) in zip(v, v[1:]):
            if a > 0 and b < a:
                out.append(((a - b) / a, uc, t, ha or hb))
    return out


def test_largest_fall_without_package_errors_is_the_stated_one():
    """'the largest one-run fall of any load-bearing number was 22.4 % (defillama_summary_virtuals
    total30d)'"""
    temiz = max(d for d in tek_kosu_dususleri() if not d[3])
    assert round(temiz[0] * 100, 1) == 22.4 and temiz[1] == "defillama_summary_virtuals"
    assert "22.4 % (defillama_summary_virtuals total30d)" in KAYNAK
    assert temiz[0] < w.DUSUS_ORANI


def test_every_fall_past_half_came_from_a_run_with_packages_missing():
    """'every fall past 50 % came from a run with packages missing'"""
    buyuk = [d for d in tek_kosu_dususleri() if d[0] > w.DUSUS_ORANI]
    assert buyuk and all(d[3] for d in buyuk)
