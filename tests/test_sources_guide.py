"""Checks guides/sources.md against collector.py and schema_map.json: every URL, constant, package
list, upstream field and stored key it names is the one the collector uses."""
import ast
import re

import pytest

import collector as c
import to_english as te
from conftest import KOK

GUIDE = (KOK / "guides" / "sources.md").read_text(encoding="utf-8")
SOURCE = (KOK / "collector.py").read_text(encoding="utf-8")
# adjacent string literals are joined by the parser, so a URL split over two lines is one constant
CONSTANTS = {n.value for n in ast.walk(ast.parse(SOURCE)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
_, KEYS = te.harita_yukle()


def ticks(text):
    return re.findall(r"`([^`]+)`", text)


def section(heading):
    part = GUIDE[GUIDE.index(heading) + len(heading):]
    return part[:part.find("\n## ")] if "\n## " in part else part


def request_table():
    rows = [ln for ln in section("# Where each number comes from").splitlines() if ln.startswith("| `")]
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in rows]


def test_table_covers_every_active_endpoint_once():
    names = [ticks(r[0])[0] for r in request_table()]
    assert sorted(names) == sorted(u[0] for u in c.UCLAR) and len(names) == len(set(names))


@pytest.mark.parametrize("cells", request_table(), ids=lambda r: ticks(r[0])[0])
def test_request_url_is_one_the_collector_uses(cells):
    url = next(t for t in ticks(cells[1]) if t.startswith("https://"))
    assert url in CONSTANTS


def test_inactive_endpoint_is_named_with_its_url():
    assert "cantina_competitions" not in [u[0] for u in c.UCLAR]
    assert "https://cantina.xyz/api/v0/competitions" in CONSTANTS and "`https://cantina.xyz/api/v0/competitions`" in GUIDE


def test_constants_have_the_stated_values():
    assert c.X402_SAYFA_TAVANI == 60 and "`X402_SAYFA_TAVANI` = 60" in GUIDE
    assert c.YARISMA_SAYFA_TAVANI == 40 and "`YARISMA_SAYFA_TAVANI` = 40" in GUIDE
    assert c.LLAMA_PROTOKOL == "virtuals-protocol" and "`LLAMA_PROTOKOL` = `virtuals-protocol`" in GUIDE
    assert "while sayfa < 10:" in SOURCE and "10 pages (the top 1,000 by popularity)" in GUIDE
    assert "time.sleep(2)" in SOURCE and "2 s apart" in GUIDE


@pytest.mark.parametrize("name, values", [("NPM_PAKETLER", c.NPM_PAKETLER), ("PYPI_PAKETLER", c.PYPI_PAKETLER),
                                          ("GH_DEPOLAR", c.GH_DEPOLAR)])
def test_package_lists_match_the_collector(name, values):
    items = section("## Packages and repositories tracked").split("\n\n")[1].split("\n- ")
    line = next(ln for ln in items if "`%s`" % name in ln)
    assert [t for t in ticks(line) if t != name] == values


def test_every_stored_key_named_is_in_the_schema_map():
    stored = set()
    for ln in section("## Upstream field → stored key").splitlines():
        stored.update(t for t in ticks(ln) if t in KEYS)
    expected = {"kaynak_sayisi", "cagri_30g", "odeyen_30g", "top10_cagri", "arastirmaci_sayisi", "omur_boyu_odeme",
                "top10", "yarisma_sayisi", "acik_yarisma", "acik_kamu", "en_yeni_baslangic_utc", "ai_total24h",
                "ai_total7d", "ai_total30d", "ai_top5_30d", "ai_30g_dagilim", "son30g_dagilim",
                "magaza_toplam_aktor", "toplam_kullanici_dagilimi", "model_sayisi", "indirme_dagilimi",
                "toplam_30g", "baslangic", "bitis", "gun", "aynasiz_toplam", "aynasiz_son30g", "yildiz", "catal",
                "izleyen", "acik_konu", "son_push"}
    assert expected <= stored


@pytest.mark.parametrize("upstream", [
    "pagination.total", "quality.l30DaysTotalCalls", "quality.l30DaysUniquePayers", "payout", "total", "ends_at",
    "private", "type_label", "starts_at", "endTime", "codeAccess", "startTime", "category", "total24h", "total7d",
    "total30d", "totalAllTime", "totalDataChart", "data.total", "stats.totalUsers", "downloads", "likes", "start",
    "end", "without_mirrors", "stargazers_count", "forks_count", "subscribers_count", "open_issues_count",
    "pushed_at", "has_next", "nextPage"])
def test_every_upstream_field_named_is_read_by_the_collector(upstream):
    assert "`%s`" % upstream in GUIDE
    assert all('"%s"' % part in SOURCE for part in upstream.split("."))
