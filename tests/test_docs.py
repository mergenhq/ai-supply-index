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
