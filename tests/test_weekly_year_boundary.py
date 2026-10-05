"""ISO weeks across year boundaries in examples/weekly_series.py. The series will cross from 2026 into
2027, and 2026 has an ISO week 53."""
import importlib.util
from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("weekly_series", KOK / "examples" / "weekly_series.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)


def satir(gun, deger, saat=7):
    t = datetime(gun.year, gun.month, gun.day, saat, tzinfo=timezone.utc)
    return {"zaman_utc": t.isoformat(), "uc": "x402_discovery", "durum": "OK", "ozet": {"kaynak_sayisi": deger}}


@pytest.mark.parametrize("stamp,hafta", [
    ("2026-12-31T07:00:00+00:00", "2026-W53"),
    ("2027-01-01T07:00:00+00:00", "2026-W53"),
    ("2027-01-03T23:59:59+00:00", "2026-W53"),
    ("2027-01-04T00:00:00+00:00", "2027-W01"),
    ("2025-12-29T07:00:00+00:00", "2026-W01"),
    ("2021-01-03T07:00:00Z", "2020-W53"),
])
def test_iso_week_label_at_year_boundaries(stamp, hafta):
    assert ws.iso_week(stamp) == hafta


@pytest.mark.parametrize("yil", range(2015, 2036))
def test_week_labels_step_one_monday_at_a_time_across_the_year(yil):
    ilk = "%d-W%02d" % date(yil, 12, 1).isocalendar()[:2]
    son = "%d-W%02d" % date(yil + 1, 1, 20).isocalendar()[:2]
    etiketler = ws._weeks(ilk, son)
    pazartesiler = [date.fromisocalendar(int(e[:4]), int(e[6:]), 1) for e in etiketler]
    assert all(b - a == timedelta(days=7) for a, b in zip(pazartesiler, pazartesiler[1:]))
    assert etiketler == sorted(etiketler) and len(set(etiketler)) == len(etiketler)
    w53 = date(yil, 12, 28).isocalendar()[1] == 53
    assert ("%d-W53" % yil in etiketler) == w53


def test_weekly_runs_through_week_53_and_into_the_new_year():
    pazartesi = date(2026, 12, 21)
    rows = [satir(pazartesi + timedelta(days=7 * i), 100 + i) for i in (0, 1, 3)]
    out = ws.weekly(rows)
    assert [e["week"] for e in out] == ["2026-W52", "2026-W53", "2027-W01", "2027-W02"]
    assert [e["value"] for e in out] == [100, 101, None, 103]
    assert out[2]["gap"] == "no rows"


def test_new_years_day_row_belongs_to_week_53_and_wins_it_when_latest():
    rows = [satir(date(2026, 12, 28), 1), satir(date(2027, 1, 1), 2), satir(date(2027, 1, 4), 3)]
    out = {e["week"]: e["value"] for e in ws.weekly(rows)}
    assert out == {"2026-W53": 2, "2027-W01": 3}
