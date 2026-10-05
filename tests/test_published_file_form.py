"""Byte-level form of the published files and completeness of each run. The byte-prefix rule between
archive snapshots and the series depends on every file having the same plain line form."""
import json

import pytest

import collector as c
from conftest import KOK

DOSYALAR = [KOK / "ai-arz-serisi.ndjson", KOK / "series-en.ndjson"] + sorted((KOK / "archive").glob("*.ndjson"))


@pytest.mark.parametrize("yol", DOSYALAR, ids=lambda p: p.name)
def test_file_is_utf8_lines_ending_in_a_newline_without_blank_lines_or_carriage_returns(yol):
    b = yol.read_bytes()
    assert b and b.endswith(b"\n") and not b.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in b and b"\n\n" not in b
    b.decode("utf-8")


@pytest.mark.parametrize("yol", DOSYALAR, ids=lambda p: p.name)
def test_every_line_is_written_the_way_the_collector_writes_it(yol):
    """collector.main() writes json.dumps(row, ensure_ascii=False) followed by a newline."""
    for no, satir in enumerate(yol.read_text(encoding="utf-8").split("\n")[:-1], 1):
        nesne = json.loads(satir)
        assert isinstance(nesne, dict), no
        assert satir == json.dumps(nesne, ensure_ascii=False), "%s line %d" % (yol.name, no)


def test_every_run_since_the_eleventh_endpoint_carries_a_row_for_each_of_the_eleven():
    """The collector writes one row per endpoint even when the endpoint fails, so a run that lacks
    one of the eleven endpoints of the 2026-08-18T16:31:07Z run was not written completely."""
    satirlar = [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()]
    ilk = min(r["zaman_utc"] for r in satirlar if r["uc"] == "code4rena_audits")
    kosular = {}
    for r in satirlar:
        if r["zaman_utc"] >= ilk:
            kosular.setdefault(r["zaman_utc"], []).append(r["uc"])
    on_bir = set(kosular[ilk])
    assert len(on_bir) == 11 and on_bir <= {u[0] for u in c.UCLAR}
    for t, ucler in kosular.items():
        assert on_bir <= set(ucler), (t, sorted(on_bir - set(ucler)))
