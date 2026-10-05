"""Figures in the README sections "First measurement — 2026-08-18" and "What stands out in week 1"
that tests/test_docs.py does not already check, recomputed from the run each one names."""
import json
import re

from conftest import KOK

README = (KOK / "README.md").read_text(encoding="utf-8")
SATIRLAR = [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()
            if x.strip()]
KAYIT = {(r["zaman_utc"], r["uc"]): r for r in SATIRLAR}
TABLO = {ln.split("|")[1].strip(): ln for ln in README.splitlines() if ln.startswith("| ")}


def ozet(etiket, uc):
    """The summary of `uc` in the run named on the README table row `etiket`."""
    m = re.search(r"`(2026-08-18T\d\d:\d\d:\d\dZ)`", TABLO[etiket])
    return KAYIT[(m.group(1).replace("Z", "+00:00"), uc)]["ozet"]


def sayi(metin):
    return float(metin.replace(",", ""))


def test_defillama_protocol_count_and_largest_protocol():
    """'$1,177,308 across 17 protocols' · '89.7 % (Virtuals Protocol, $1,055,670)'"""
    o = ozet("DefiLlama (AI-Agents category)", "defillama_fees_ai_agents")
    assert "across **17** protocols" in TABLO["DefiLlama (AI-Agents category)"]
    assert o["ai_agent_protokol_sayisi"] == 17
    satir = TABLO["→ concentration"]
    m = re.search(r"\((.+?), \$([\d,]+)\)", satir)
    en_buyuk = o["ai_top5_30d"][0]
    assert m and en_buyuk["ad"] == m.group(1) and round(en_buyuk["usd30d"]) == sayi(m.group(2))


def test_remaining_protocols_share():
    """'The remaining 16 protocols share roughly $121,600 between them.'"""
    o = ozet("DefiLlama (AI-Agents category)", "defillama_fees_ai_agents")
    m = re.search(r"remaining (\d+) protocols share roughly \$([\d,]+)", README)
    kalan = o["ai_total30d"] - o["ai_top5_30d"][0]["usd30d"]
    assert int(m.group(1)) == o["ai_agent_protokol_sayisi"] - 1
    assert abs(kalan - sayi(m.group(2))) < 100


def test_sherlock_researchers_and_payouts():
    """'1,710 researchers · $15,762,894 lifetime' · '$15.8 M has been distributed'"""
    o = ozet("Sherlock (security-audit contests)", "sherlock_leaderboard")
    assert "**1,710** researchers" in TABLO["Sherlock (security-audit contests)"]
    assert o["arastirmaci_sayisi"] == 1710
    assert "$15.8 M has been" in README and round(o["omur_boyu_odeme"]["toplam"] / 1e6, 1) == 15.8


def test_sherlock_contests_listed():
    """'301 (open right now: 0)' · 'Of 301 audit contests listed on Sherlock, zero are open'"""
    o = ozet("Sherlock contests", "sherlock_contests")
    assert "**301**" in TABLO["Sherlock contests"] and "Of 301 audit contests" in README
    assert o["yarisma_sayisi"] == 301 and o["acik_yarisma"] == 0


def test_x402_calls():
    """'15,149 · 30d calls 322,375'"""
    o = ozet("x402 (agent payment discovery)", "x402_discovery")
    m = re.search(r"30d calls \*\*([\d,]+)\*\*", TABLO["x402 (agent payment discovery)"])
    assert m and o["cagri_30g"]["toplam"] == sayi(m.group(1))


def test_github_stars_of_every_named_repository():
    """'AutoGPT 186,664 ★ · langchain 144,478 ★ · MCP servers 89,659 ★'"""
    o = ozet("GitHub", "github_repos")
    adlar = {"AutoGPT": "Significant-Gravitas/AutoGPT", "langchain": "langchain-ai/langchain",
             "MCP servers": "modelcontextprotocol/servers"}
    yildizlar = dict(re.findall(r"(AutoGPT|langchain|MCP servers) ([\d,]+) ★", TABLO["GitHub"]))
    assert set(yildizlar) == set(adlar)
    for ad, depo in adlar.items():
        assert o[depo]["yildiz"] == sayi(yildizlar[ad]), ad


def test_code4rena_rows_start_with_the_named_run_and_the_table_uses_earlier_runs():
    """'Its rows enter the series from the 2026-08-18T16:31:07Z run onward — this table deliberately
    reports only rows from earlier runs.'"""
    m = re.search(r"series from the `(2026-08-18T\d\d:\d\d:\d\dZ)` run onward", README)
    ilk = min(r["zaman_utc"] for r in SATIRLAR if r["uc"] == "code4rena_audits")
    assert m and ilk == m.group(1).replace("Z", "+00:00")
    for satir in TABLO.values():
        for t in re.findall(r"`(2026-08-18T\d\d:\d\d:\d\dZ)`", satir):
            assert t < m.group(1)
