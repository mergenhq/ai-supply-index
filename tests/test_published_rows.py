"""Row and run structure of the published series: order, runs, status fields and the watchdog's
load-bearing numbers. The series and the archive snapshots are only read."""
import json
import re
from datetime import datetime

import pytest

import collector as c
import freshness_watchdog as w
from conftest import KOK

SATIRLAR = [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()
            if x.strip()]
DAMGA = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00")


def test_every_stamp_is_utc_to_the_second():
    assert all(DAMGA.fullmatch(r["zaman_utc"]) for r in SATIRLAR)


def test_rows_are_in_time_order_and_each_run_is_one_block():
    damgalar = [r["zaman_utc"] for r in SATIRLAR]
    assert damgalar == sorted(damgalar)
    bloklar = [d for i, d in enumerate(damgalar) if i == 0 or d != damgalar[i - 1]]
    assert len(bloklar) == len(set(bloklar))


def test_each_run_has_one_collector_version_and_one_collector_name():
    kosular = {}
    for r in SATIRLAR:
        kosular.setdefault(r["zaman_utc"], set()).add((r.get("surum"), r.get("toplayici")))
    assert all(len(v) == 1 for v in kosular.values())


def test_each_snapshot_was_taken_after_its_last_run():
    for p in sorted((KOK / "archive").glob("ai-arz-serisi-*.ndjson")):
        damga = datetime.strptime(p.name[len("ai-arz-serisi-"):-len(".ndjson")], "%Y%m%dT%H%M%SZ")
        son = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()][-1]
        assert damga.isoformat() + "+00:00" > son["zaman_utc"], p.name


# ── status fields ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("r", [r for r in SATIRLAR if r.get("durum") != "OK"],
                         ids=lambda r: "%s:%s" % (r["zaman_utc"], r["uc"]))
def test_a_failed_row_says_how_it_failed(r):
    d = r["durum"]
    if d == "HATA":
        assert isinstance(r.get("hata"), str) and r["hata"] and "ozet" not in r
    elif d == "HTTP-HATA":
        assert type(r.get("http")) is int and "ozet" not in r
    elif d == "HATA-ICERIDE":
        assert c.hata_iceride(r.get("ozet"))
    else:
        pytest.fail("unknown durum %r" % d)


def test_an_ok_row_has_a_summary_without_a_top_level_error():
    for r in SATIRLAR:
        if r.get("durum") == "OK":
            assert isinstance(r.get("ozet"), dict) and not r["ozet"].get("hata"), (r["zaman_utc"], r["uc"])


# ── the watchdog's load-bearing numbers ─────────────────────────────────────
def test_no_usable_row_has_a_zero_or_missing_load_bearing_number():
    """The watchdog treats 0 or None as a broken schema because no usable row has ever had one."""
    for r in SATIRLAR:
        o = r.get("ozet")
        if r.get("durum") != "OK" or not isinstance(o, dict) or "olculemedi" in o or r["uc"] not in w.TASIYICILAR:
            continue
        v = w.TASIYICILAR[r["uc"]](o)
        assert v not in (0, None), (r["zaman_utc"], r["uc"], v)
