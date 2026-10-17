"""Checks guides/english-mirror.md: its key tables agree with schema_map.json, and its code gives on
series-en.ndjson the same weekly values as examples/weekly_series.py gives on ai-arz-serisi.ndjson."""
import importlib.util
import re

import pytest

import to_english as te
from conftest import KOK

_spec = importlib.util.spec_from_file_location("weekly_series", KOK / "examples" / "weekly_series.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

GUIDE = (KOK / "guides" / "english-mirror.md").read_text(encoding="utf-8")
_, KEYS = te.harita_yukle()


def table(heading):
    lines = GUIDE[GUIDE.index(heading):].splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("|"))
    block = []
    for ln in lines[start:]:
        if not ln.startswith("|"):
            break
        block.append([c.strip() for c in ln.strip("|").split("|")])
    return block[2:]


def ticks(cell):
    return re.findall(r"`([^`]+)`", cell)


def run_guide_code(monkeypatch):
    part = GUIDE[GUIDE.index("```python") + len("```python"):]
    code = part[:part.index("```")]
    monkeypatch.chdir(KOK)
    ns = {}
    exec(compile(code, "guides/english-mirror.md", "exec"), ns)
    return ns


@pytest.mark.parametrize("cells", table("## Keys and values you need"), ids=lambda c: ticks(c[0])[0])
def test_key_table_matches_the_schema_map(cells):
    assert KEYS[ticks(cells[0])[0]] == ticks(cells[1])[0]


def test_value_path_table_translates_what_the_weekly_tools_read():
    rows = table("## Where the weekly value is")
    assert sorted(ticks(r[0])[0] for r in rows) == sorted(ws.VALUES)
    turkish = {"kaynak_sayisi", "arastirmaci_sayisi", "acik_yarisma", "ai_total30d", "total30d",
               "magaza_toplam_aktor", "indirme_dagilimi", "toplam", "toplam_30g", "aynasiz_toplam", "yildiz"}
    english = {KEYS[k] for k in turkish}
    for r in rows:
        for path in ticks(r[1]):
            assert set(path.split(".")) <= english, path


def test_status_values_listed_are_the_ones_in_the_schema_map():
    listed = set(ticks(table("## Keys and values you need")[2][2]))
    durum_desc = next(k[3] for g in te.harita_yukle()[0]["groups"] for k in g["keys"] if k[0] == "durum")
    assert listed == {p.split()[0] for p in durum_desc.split("|") if p.strip()}


def test_guide_code_gives_the_weekly_series_values(monkeypatch):
    ns = run_guide_code(monkeypatch)
    ours = {(e["week"], e["endpoint"]): (e["value"], e["timestamp_utc"]) for e in ns["weekly"]}
    want = {(e["week"], e["endpoint"]): (e["value"], e["zaman_utc"])
            for e in ws.weekly(ws.read_rows(KOK / "ai-arz-serisi.ndjson")) if e["value"] is not None}
    assert ours and ours == want


def test_guide_code_rules_on_english_rows(monkeypatch):
    ns = run_guide_code(monkeypatch)
    v = ns["weekly_value"]
    ok = {"timestamp_utc": "t", "endpoint": "x402_discovery", "status": "OK", "summary": {"resource_count": 5}}
    assert v(ok) == 5
    assert v(dict(ok, status="HATA")) is None
    assert v(dict(ok, summary={"resource_count": 0, "unmeasurable": "schema broken"})) is None
    pkg = {"timestamp_utc": "t", "endpoint": "npm_downloads", "status": "OK",
           "summary": {"a": {"downloads_30d": 3}, "b": {"downloads_30d": 4}}}
    assert v(pkg) == 7
    assert v(dict(pkg, summary={"a": {"downloads_30d": 3}, "b": {"error": "HTTPError 429"}})) is None
    assert v(dict(pkg, summary={"a": {"downloads_30d": 3, "unmeasurable": "x"}})) is None
    assert v({"endpoint": "sherlock_contests", "status": "OK", "summary": {"open_count": 0}}) == 0
