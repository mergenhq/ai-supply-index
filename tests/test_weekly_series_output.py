"""Text output of examples/weekly_series.py: every printed value carries what it measures, and the
printed number is the value weekly() picked. Synthetic series under tmp_path."""
import importlib.util
import json
import re

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("weekly_series", KOK / "examples" / "weekly_series.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

OZET = {
    "x402_discovery": {"kaynak_sayisi": 15149},
    "sherlock_contests": {"acik_yarisma": 0},
    "hf_models": {"indirme_dagilimi": {"toplam": 1580224158}},
    "npm_downloads": {"a": {"toplam_30g": 5}, "b": {"toplam_30g": 7}},
}


def seri(tmp_path):
    p = tmp_path / "s.ndjson"
    p.write_text("".join(json.dumps({"zaman_utc": "2026-08-18T07:00:00+00:00", "uc": uc, "durum": "OK",
                                     "ozet": o}) + "\n" for uc, o in OZET.items()), encoding="utf-8")
    return p


def test_each_text_line_names_what_its_value_measures(tmp_path, capsys):
    assert ws.main(["--series", str(seri(tmp_path))]) == 0
    satirlar = capsys.readouterr().out.splitlines()
    assert len(satirlar) == len(OZET)
    for s in satirlar:
        uc = s.split()[1]
        assert s.endswith("[%s]" % ws.VALUES[uc][0]), s
        assert "<function" not in s


@pytest.mark.parametrize("uc,yazi", [("x402_discovery", "15,149"), ("sherlock_contests", "0"),
                                     ("hf_models", "1,580,224,158"), ("npm_downloads", "12")])
def test_printed_number_is_the_picked_value(tmp_path, capsys, uc, yazi):
    ws.main(["--series", str(seri(tmp_path)), "--endpoint", uc])
    s = capsys.readouterr().out.strip()
    assert re.search(r"\s%s\s+2026-08-18T07:00:00\+00:00" % re.escape(yazi), s), s
