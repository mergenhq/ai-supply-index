"""Checks guides/reading-the-values.md against the code and the published series: the table covers
every endpoint the weekly tools know, the named fields exist, and every *(series)* statement holds on
the published rows up to 2026-09-28T23:59:59, the period the guide names."""
import importlib.util
import re

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("weekly_series", KOK / "examples" / "weekly_series.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

GUIDE = (KOK / "guides" / "reading-the-values.md").read_text(encoding="utf-8")
# the guide's (series) statements describe the rows up to this time; later weekly rows do not change them
CUTOFF = "2026-09-28T23:59:59"
ROWS = [r for r in ws.read_rows(KOK / "ai-arz-serisi.ndjson") if r.get("zaman_utc", "") <= CUTOFF]
WEEKLY = ws.weekly(ROWS)


def table(heading):
    lines = GUIDE[GUIDE.index(heading):].splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("|"))
    block = []
    for ln in lines[start:]:
        if not ln.startswith("|"):
            break
        block.append([c.strip() for c in ln.strip("|").split("|")])
    return block[2:]                                  # skip the header and the separator row


def ticks(cell):
    return re.findall(r"`([^`]+)`", cell)


def weekly_values(endpoint):
    return [e["value"] for e in WEEKLY if e["endpoint"] == endpoint and e["value"] is not None]


def usable_rows(endpoint):
    return [r for r in ROWS if r.get("uc") == endpoint and ws.value(r) is not None]


def has_path(ozet, path):
    v = ozet
    for k in path.split("."):
        if not isinstance(v, dict) or k not in v:
            return False
        v = v[k]
    return True


VALUE_TABLE = table("## What the weekly value is")


def test_value_table_covers_every_endpoint_once():
    names = [ticks(r[0])[0] for r in VALUE_TABLE]
    assert sorted(names) == sorted(ws.VALUES) and len(names) == len(set(names))


@pytest.mark.parametrize("cells", VALUE_TABLE, ids=lambda c: ticks(c[0])[0])
def test_weekly_value_field_is_what_the_weekly_tools_read(cells):
    endpoint, field = ticks(cells[0])[0], ticks(cells[1])[0]
    for r in usable_rows(endpoint):
        o = r["ozet"]
        if endpoint in ("npm_downloads", "pypi_downloads", "github_repos"):
            subs = [v for v in o.values() if isinstance(v, dict)]
            assert subs and all(field in v for v in subs)
            assert ws.value(r) == sum(v[field] for v in subs)
        else:
            assert has_path(o, field)
            v = o
            for k in field.split("."):
                v = v[k]
            assert ws.value(r) == v


@pytest.mark.parametrize("cells", table("## Picking the right field for a question"), ids=lambda c: c[0][:30])
def test_question_fields_exist_in_the_published_series(cells):
    endpoint = ticks(cells[2])[0]
    for field in ticks(cells[1]):
        if endpoint in ("npm_downloads", "pypi_downloads"):
            assert any(field in v for r in usable_rows(endpoint) for v in r["ozet"].values() if isinstance(v, dict))
        else:
            assert any(has_path(r["ozet"], field) for r in usable_rows(endpoint)), field


# ── every *(series)* statement ──────────────────────────────────────────────
def falls_somewhere(seq):
    return any(b < a for a, b in zip(seq, seq[1:]))


def test_x402_resource_count_falls_in_some_weeks():
    assert falls_somewhere(weekly_values("x402_discovery"))


def test_defillama_category_has_17_18_and_19_protocols():
    counts = {r["ozet"].get("ai_agent_protokol_sayisi") for r in usable_rows("defillama_fees_ai_agents")}
    assert counts == {17, 18, 19}


def test_a_hugging_face_models_downloads_fall_between_weeks():
    per_model = {}
    for r in sorted(usable_rows("hf_models"), key=lambda r: r["zaman_utc"]):
        for m in r["ozet"].get("top10", []):
            per_model.setdefault(m["id"], []).append(m["indirme"])
    assert any(falls_somewhere(v) for v in per_model.values())


def test_npm_window_is_30_days_in_every_row():
    days = {v["gun"] for r in usable_rows("npm_downloads") for v in r["ozet"].values() if isinstance(v, dict)}
    assert days == {30}


def test_pypi_window_is_about_183_days():
    days = {v["aynasiz_gun"] for r in usable_rows("pypi_downloads") for v in r["ozet"].values() if isinstance(v, dict)}
    assert days and all(178 <= d <= 188 for d in days)
    assert "about 183 days" in GUIDE


def test_a_repositorys_stars_fall_in_some_weeks():
    per_repo = {}
    for r in sorted(usable_rows("github_repos"), key=lambda r: r["zaman_utc"]):
        for name, v in r["ozet"].items():
            if isinstance(v, dict):
                per_repo.setdefault(name, []).append(v["yildiz"])
    assert any(falls_somewhere(v) for v in per_repo.values())


@pytest.mark.parametrize("endpoint", ["sherlock_contests", "code4rena_audits"])
def test_open_count_is_zero_in_every_week(endpoint):
    values = weekly_values(endpoint)
    assert values and set(values) == {0}


def test_guide_names_the_period_it_was_measured_on():
    first = min(r["zaman_utc"] for r in ROWS)[:10]
    last = max(r["zaman_utc"] for r in ROWS)[:10]
    assert "(%s to %s)" % (first, last) in GUIDE
