"""Checks that the documentation states what the code and the published series actually do."""
import inspect
import json
import re

import collector as c
from conftest import KOK

README = (KOK / "README.md").read_text(encoding="utf-8")
HARITA = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))


def aciklama(tr):
    for g in HARITA["groups"]:
        for satir in g["keys"]:
            if satir[0] == tr:
                return satir[3]
    raise KeyError(tr)


def grup_notu(ad):
    return next(g["note"] for g in HARITA["groups"] if g["name"] == ad)


def seri():
    return [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()]


def test_top10_share_states_the_small_n_case():
    # with ten or fewer non-zero values the share is 1.0 by construction
    assert c.dagilim_ozeti([0, 0, 5, 3], [1])["top10_pay"] == 1.0
    assert "1.0" in aciklama("top10_pay") and "ten or fewer" in aciklama("top10_pay")


def test_fixed_defillama_protocol_is_described_as_fixed():
    notu = dict((u[0], u[2]) for u in c.UCLAR)["defillama_summary_virtuals"]
    assert "fixed" in notu and "centre of concentration" not in notu
    assert "centre of concentration" not in (c.uc_defillama_protokol.__doc__ or "")


def test_hugging_face_sample_is_not_described_as_agent_models():
    # the request has no filter: it is the top 100 models on the Hub by downloads
    kaynak = inspect.getsource(c.uc_hf_modeller)
    assert "huggingface.co/api/models?sort=downloads" in kaynak and "filter=" not in kaynak
    assert "AI-agent models" not in README


def test_pypi_window_matches_the_series():
    son = [r for r in seri() if r["uc"] == "pypi_downloads"][-1]["ozet"]
    gun = max(v["aynasiz_gun"] for v in son.values() if isinstance(v, dict) and "aynasiz_gun" in v)
    m = re.search(r"roughly (\d+) days", grup_notu("PyPI downloads"))
    assert m and abs(int(m.group(1)) - gun) <= 10, (m and m.group(1), gun)
    assert "362" not in (c.uc_pypi.__doc__ or "")


def test_apify_note_and_sample_size():
    notu = dict((u[0], u[2]) for u in c.UCLAR)["apify_store"]
    assert "SLIDING" not in notu and "cumulative" in notu
    assert "scanned" in grup_notu("Apify store")
    sinir = README[README.index("2. **Sampling where the source paginates.**"):]
    assert "taranan" in sinir.split("\n3. ")[0]


def test_defillama_is_described_as_fees_not_revenue():
    dl = next(g for g in HARITA["groups"] if g["name"] == "DeFiLlama")
    metin = (dl["note"] + " ".join(k[3] for k in dl["keys"])).lower()
    assert "not protocol revenue" in metin
    assert "revenue" not in metin.replace("not protocol revenue", "")
    ust = README[:README.index("## Method")]
    assert "revenue" not in ust.lower()


def test_readme_describes_the_test_suite():
    assert "python3 -m pytest" in README
    assert "Every script self-tests" not in README


# ── first-measurement table: every figure names the run it comes from ─────
ILK_OLCUM = [
    # (row label, endpoint, path into ozet, value as printed in the README)
    ("DefiLlama (AI-Agents category)", "defillama_fees_ai_agents", ("ai_total30d",), 1177308.67),
    ("→ concentration", "defillama_fees_ai_agents", ("ai_30g_dagilim", "top1_pay"), 0.8967),
    ("Sherlock (security-audit contests)", "sherlock_leaderboard", ("omur_boyu_odeme", "toplam"), 15762894.38),
    ("Sherlock contests", "sherlock_contests", ("acik_yarisma",), 0),
    ("x402 (agent payment discovery)", "x402_discovery", ("kaynak_sayisi",), 15149),
    ("Apify store", "apify_store", ("magaza_toplam_aktor",), 47257),
    ("Hugging Face", "hf_models", ("indirme_dagilimi", "toplam"), 1580224158.0),
    ("npm / PyPI", "npm_downloads", ("@anthropic-ai/sdk", "toplam_30g"), 115914002),
    ("GitHub", "github_repos", ("Significant-Gravitas/AutoGPT", "yildiz"), 186664),
]


def test_first_measurement_rows_name_their_run_and_match_it():
    satirlar = {ln.split("|")[1].strip(): ln for ln in README.splitlines() if ln.startswith("| ")}
    kayit = {(r["zaman_utc"], r["uc"]): r for r in seri()}
    for etiket, uc, yol, beklenen in ILK_OLCUM:
        ln = satirlar[etiket]
        m = re.search(r"`(2026-08-18T\d\d:\d\d:\d\dZ)`", ln)
        assert m, "no run timestamp on row %r" % etiket
        o = kayit[(m.group(1).replace("Z", "+00:00"), uc)]["ozet"]
        for k in yol:
            o = o[k]
        assert o == beklenen, (etiket, o)


def test_readme_has_no_stale_age_claims():
    assert "days old" not in README
    assert "Its rows enter the\nseries with the next weekly run" not in README


def test_note_description_names_the_last_turkish_run():
    turkce = ("arsivli", "kesiti", "kategorisi", "nobeti", "gunluk", "basina")
    son = max(r["zaman_utc"] for r in seri() if any(t in r["not"] for t in turkce))
    assert son.replace("+00:00", "Z") in aciklama("not")


def test_url_description_covers_open_entries():
    assert "open entr" in aciklama("url")
    assert "later versions record it in" not in aciklama("url")


def test_licence_files_name_existing_files_and_cover_the_published_data():
    for ad in ("LICENSE-DATA", "LICENSE"):
        metin = (KOK / ad).read_text(encoding="utf-8")
        for dosya in re.findall(r"`([^`]+\.(?:py|sh|json|ndjson))`", metin):
            assert list(KOK.glob(dosya)), "%s names a missing file: %s" % (ad, dosya)
    veri = (KOK / "LICENSE-DATA").read_text(encoding="utf-8")
    for gerekli in ("ai-arz-serisi.ndjson", "series-en.ndjson", "archive/", "*.ots"):
        assert gerekli in veri, gerekli


# ── repository hygiene checked in CI ────────────────────────────────────────
def test_readme_schema_section_is_the_generated_one():
    import to_english as te
    a = README.index("## Schema\n\n") + len("## Schema\n\n")
    b = README.index("### Why the keys stay Turkish")
    assert README[a:b] == te.sema_md() + "\n"


def test_english_mirror_is_up_to_date(tmp_path, capsys):
    import to_english as te
    meta, keys = te.harita_yukle()
    cikti = tmp_path / "en.ndjson"
    te.ingilizce_yaz(KOK / "ai-arz-serisi.ndjson", cikti, keys, meta)
    assert cikti.read_bytes() == (KOK / "series-en.ndjson").read_bytes()


def test_scripts_with_a_shebang_are_executable():
    import os
    for ad in ("collector.py", "freshness_watchdog.py", "to_english.py", "run_weekly.sh"):
        assert os.access(KOK / ad, os.X_OK), ad


def test_ci_workflow_runs_the_suite_and_the_self_tests():
    wf = (KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    for adim in ("python -m pytest", "freshness_watchdog.py --self-test", "to_english.py --self-test",
                 "shellcheck run_weekly.sh"):
        assert adim in wf, adim


def test_reproduce_section_does_not_append_to_the_published_series():
    blok = README[README.index("## Reproduce it"):]
    blok = blok[:blok.index("```", blok.index("```") + 3)]
    assert "collector.py --out" in blok


def test_using_the_series_example_runs(tmp_path, monkeypatch):
    bolum = README[README.index("## Using the series"):]
    kod = bolum[bolum.index("```python") + len("```python"):]
    kod = kod[:kod.index("```")]
    monkeypatch.chdir(KOK)
    ns = {}
    exec(compile(kod, "README:Using the series", "exec"), ns)
    haftalik = ns["weekly"]
    # one row per (ISO week, endpoint); only OK rows without olculemedi
    assert len({(h["week"], h["uc"]) for h in haftalik}) == len(haftalik)
    assert all(h["durum"] == "OK" and "olculemedi" not in (h.get("ozet") or {}) for h in haftalik)
    assert {"2026-W34", "2026-W40"} <= {h["week"] for h in haftalik}


def test_record_link_keeps_its_wording():
    satir = next(ln for ln in README.splitlines() if "](record/)" in ln)
    assert "of what this system measured about itself" in satir
