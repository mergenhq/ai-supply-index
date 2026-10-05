"""Statements in the key descriptions of schema_map.json that can be checked against the published
series. Each test quotes the description it checks. Files are only read."""
import collections
import json
import re

from conftest import KOK

HARITA = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))
ACIKLAMA = {k[0]: k[3] for g in HARITA["groups"] for k in g["keys"]}
INGILIZCE = {k[0]: k[1] for g in HARITA["groups"] for k in g["keys"]}
SATIRLAR = [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()
            if x.strip()]


def nesneler(kosul):
    out = []

    def gez(o, ebeveyn):
        if isinstance(o, dict):
            if kosul(o):
                out.append(o)
            for k, v in o.items():
                gez(v, k)
        elif isinstance(o, list):
            for v in o:
                gez(v, ebeveyn)
    for r in SATIRLAR:
        gez(r, None)
    return out


def test_top10_share_is_one_when_ten_or_fewer_values_are_non_zero():
    """top10_pay: 'it is 1.0 by construction whenever there are ten or fewer non-zero values
    (n minus zero_count)'"""
    assert "ten or fewer non-zero values" in ACIKLAMA["top10_pay"]
    for o in nesneler(lambda o: "top10_pay" in o):
        if o["n"] - o["sifir_sayisi"] <= 10:
            assert o["top10_pay"] == 1.0, o


def test_inside_remarks_name_the_object_the_key_lives_in():
    """e.g. cagri: 'call count for one resource (inside top10_by_calls)'"""
    ebeveynler = collections.defaultdict(set)

    def gez(o, ebeveyn):
        if isinstance(o, dict):
            for k, v in o.items():
                ebeveynler[k].add(ebeveyn)
                gez(v, k)
        elif isinstance(o, list):
            for v in o:
                gez(v, ebeveyn)
    for r in SATIRLAR:
        gez(r, None)
    icinde = {k: m.group(1) for k, a in ACIKLAMA.items() for m in [re.search(r"\(inside (\w+)\)", a)] if m}
    assert icinde
    for k, ad in icinde.items():
        assert ebeveynler[k], "%s does not occur in the series" % k
        assert {INGILIZCE.get(p, p) for p in ebeveynler[k]} == {ad}, (k, ebeveynler[k], ad)


def test_truncated_text_fields_stay_within_their_stated_length():
    """kaynak and baslik: 'truncated to 120 characters'"""
    for k in ("kaynak", "baslik"):
        m = re.search(r"truncated to (\d+) characters", ACIKLAMA[k])
        assert m, k
        sinir = int(m.group(1))
        degerler = [o[k] for o in nesneler(lambda o, k=k: k in o)]
        assert all(isinstance(v, str) and len(v) <= sinir for v in degerler), k


def test_lists_described_as_ten_or_five_largest_hold_at_most_that_many():
    """top10, top10_cagri: 'the ten ...'; ai_top5_30d: 'five largest ...'"""
    for k, n in (("top10", 10), ("top10_cagri", 10), ("ai_top5_30d", 5)):
        assert ("ten" if n == 10 else "five") in ACIKLAMA[k]
        listeler = [o[k] for o in nesneler(lambda o, k=k: k in o)]
        assert listeler and all(isinstance(x, list) and len(x) <= n for x in listeler), k
