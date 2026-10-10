"""Every key in the published series holds a value of the type that schema_map.json documents for it
(the type column of the README Schema tables). Keys that are data, not schema (histogram buckets and
package identifiers), are skipped as schema_map.json's passthrough section describes."""
import json
import re
from datetime import date, datetime

import pytest

from conftest import KOK

HARITA = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))
TIPLER = {k[0]: k[2] for g in HARITA["groups"] for k in g["keys"]}
PAKET_UC = set(HARITA["passthrough"]["package_identifiers"]["endpoints"])
SATIRLAR = [json.loads(x) for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()
            if x.strip()]


def iso_utc(v):
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d.utcoffset() is not None and d.utcoffset().total_seconds() == 0


def gun(v):
    return bool(re.fullmatch(r"\d{4}-\d\d-\d\d", v)) and date.fromisoformat(v) is not None


def sayi(v):
    return type(v) in (int, float)


TEMEL = {
    "integer": lambda v: type(v) is int,
    "number": sayi,
    "string": lambda v: type(v) is str,
    "boolean": lambda v: type(v) is bool,
    "object": lambda v: type(v) is dict,
    "array": lambda v: type(v) is list,
    "null": lambda v: v is None,
}
AYRINTI = {
    "date": gun,
    "ISO-8601, UTC": iso_utc,
    "0-1": lambda v: 0 <= v <= 1,
    "seconds": lambda v: v >= 0,
    "days": sayi,                 # units: no further constraint
    "USD": sayi,
    "reason": lambda v: bool(v),
    "distribution": lambda v: "n" in v,
}


def uyar(tip, v):
    """True when value v matches a schema_map.json type such as 'string (date) | null'."""
    for parca in tip.split("|"):
        m = re.fullmatch(r"\s*(\w+)(?:\s*\((.+)\))?\s*", parca)
        assert m and m.group(1) in TEMEL, "type text not understood: %r" % tip
        if TEMEL[m.group(1)](v) and (m.group(2) is None or AYRINTI[m.group(2)](v)):
            return True
    return False


def test_every_type_text_is_understood():
    for tip in set(TIPLER.values()):
        for parca in tip.split("|"):
            m = re.fullmatch(r"\s*(\w+)(?:\s*\((.+)\))?\s*", parca)
            assert m and m.group(1) in TEMEL and (m.group(2) is None or m.group(2) in AYRINTI), tip


def degerler(r):
    """(path, key, value) for every schema key in a row, skipping data keys."""
    out = []

    def gez(o, yol):
        if isinstance(o, dict):
            for k, v in o.items():
                veri = (yol and yol[-1] == "histogram") or (yol == ["ozet"] and r.get("uc") in PAKET_UC)
                if not veri:
                    out.append(("/".join(yol + [k]), k, v))
                gez(v, yol + [k])
        elif isinstance(o, list):
            for v in o:
                gez(v, yol)
    gez(r, [])
    return out


@pytest.mark.parametrize("no,r", [pytest.param(no, r, id="line%d" % no) for no, r in enumerate(SATIRLAR, 1)])
def test_every_value_has_its_documented_type(no, r):
    for yol, k, v in degerler(r):
        assert k in TIPLER, "line %d: %s is not in schema_map.json" % (no, yol)
        assert uyar(TIPLER[k], v), "line %d: %s = %r is not %s" % (no, yol, v, TIPLER[k])


def test_type_checker_rejects_mismatches():
    assert not uyar("integer", True) and not uyar("integer", 1.5) and not uyar("integer", "1")
    assert not uyar("string (date)", "2026-08-18T07:00:00") and not uyar("number (0-1)", 1.4)
    assert not uyar("string (ISO-8601, UTC)", "2026-08-18T07:00:00+02:00")
    assert uyar("integer | null", None) and uyar("string | integer", 3) and uyar("number", 2)
