"""The README, schema_map.json, the weekly example and the collector describe the same things.
Only files in the repository are read."""
import importlib.util
import json
import re

import collector as c
from conftest import KOK

README = (KOK / "README.md").read_text(encoding="utf-8")
HARITA = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))

_spec = importlib.util.spec_from_file_location("weekly_series", KOK / "examples" / "weekly_series.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)


def readme_snippet_weekly(monkeypatch):
    bolum = README[README.index("## Using the series"):]
    kod = bolum[bolum.index("```python") + len("```python"):]
    kod = kod[:kod.index("```")]
    monkeypatch.chdir(KOK)
    ns = {}
    exec(compile(kod, "README:Using the series", "exec"), ns)
    return ns["weekly"]


def test_weekly_example_picks_the_same_rows_as_the_readme_snippet(monkeypatch):
    snippet = {(r["week"], r["uc"]): r["zaman_utc"] for r in readme_snippet_weekly(monkeypatch)}
    ornek = {(e["week"], e["endpoint"]): e["zaman_utc"]
             for e in ws.weekly(ws.read_rows(KOK / "ai-arz-serisi.ndjson")) if "gap" not in e}
    assert snippet and ornek == snippet


def test_weekly_example_reads_every_endpoint_the_collector_writes():
    assert set(ws.VALUES) == {u[0] for u in c.UCLAR}


def test_every_documented_key_is_in_the_series_or_written_by_the_collector():
    seri = (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8")
    kaynak = (KOK / "collector.py").read_text(encoding="utf-8")
    for g in HARITA["groups"]:
        for k in g["keys"]:
            ad = '"%s"' % k[0]
            assert ad in seri or ad in kaynak, "%s (%s) is documented but never written" % (k[0], g["name"])


SONEK = ("_discovery", "_leaderboard", "_contests", "_audits", "_competitions", "_agents", "_virtuals",
         "_store", "_models", "_downloads", "_repos")


def test_endpoint_names_in_group_notes_are_collector_endpoints():
    bilinen = {u[0] for u in c.UCLAR} | {"cantina_competitions"}
    assert callable(c.uc_cantina_competitions)
    for g in HARITA["groups"]:
        for ad in re.findall(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b", g["note"]):
            if ad.endswith(SONEK):
                assert ad in bilinen, "%s names an unknown endpoint: %s" % (g["name"], ad)


def test_package_identifier_endpoints_are_collector_endpoints():
    assert set(HARITA["passthrough"]["package_identifiers"]["endpoints"]) <= {u[0] for u in c.UCLAR}
