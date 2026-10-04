#!/usr/bin/env python3
"""validate_series.py — structural checks for an AI Supply Index series file.

Every line must be a JSON object, and every row is checked against schema_map.json, the file the
README "Schema" tables are generated from:
  envelope    every top-level key is one of the "Record envelope" keys, with that key's type
              (string, object, number, integer); zaman_utc, uc, not and durum are present
  zaman_utc   parses as an ISO-8601 time with a UTC offset
  uc          the endpoint name appears in schema_map.json
  durum       one of the values listed for durum in schema_map.json (OK, HATA, HTTP-HATA,
              HATA-ICERIDE)
It prints the number of rows per durum and per endpoint, then the problems found, and exits
with 1 when any row fails a check (0 when none does, 2 when a file cannot be read).

Standard library only. Usage:
    python3 examples/validate_series.py
    python3 examples/validate_series.py --series other.ndjson --json
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERIES = ROOT / "ai-arz-serisi.ndjson"
DEFAULT_MAP = ROOT / "schema_map.json"
REQUIRED = ("zaman_utc", "uc", "not", "durum")

# schema_map.json type text -> accepted Python types (bool is never a number here)
_TYPES = {"string": (str,), "object": (dict,), "number": (int, float), "integer": (int,)}


class Rules:
    """What a row is checked against, read from schema_map.json."""

    def __init__(self, map_path=DEFAULT_MAP):
        text = Path(map_path).read_text(encoding="utf-8")
        m = json.loads(text)
        envelope = next(g for g in m["groups"] if g["name"] == "Record envelope")
        self.types = {}
        for key, _en, typ, desc in envelope["keys"]:
            self.types[key] = _TYPES[typ.split()[0]]
            if key == "durum":
                self.durum = {part.split()[0] for part in desc.split("|") if part.strip()}
        self._text = text

    def known_endpoint(self, uc):
        pat = r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(uc)
        return re.search(pat, self._text) is not None


def _is_type(v, accepted):
    return isinstance(v, accepted) and not isinstance(v, bool)


def check_row(row, rules):
    """List of (check, message) for one parsed row; empty when the row passes."""
    if not isinstance(row, dict):
        return [("json", "not a JSON object")]
    out = []
    for k in REQUIRED:
        if k not in row:
            out.append(("envelope", "missing key %r" % k))
    for k, v in row.items():
        if k not in rules.types:
            out.append(("envelope", "unknown key %r" % k))
        elif not _is_type(v, rules.types[k]):
            out.append(("envelope", "key %r has type %s" % (k, type(v).__name__)))
    z = row.get("zaman_utc")
    if isinstance(z, str):
        try:
            if datetime.fromisoformat(z.replace("Z", "+00:00")).utcoffset() is None:
                out.append(("zaman_utc", "zaman_utc %r has no UTC offset" % z))
        except ValueError:
            out.append(("zaman_utc", "zaman_utc %r is not an ISO-8601 time" % z))
    uc = row.get("uc")
    if isinstance(uc, str) and not rules.known_endpoint(uc):
        out.append(("uc", "endpoint %r does not appear in schema_map.json" % uc))
    d = row.get("durum")
    if isinstance(d, str) and d not in rules.durum:
        out.append(("durum", "unknown durum %r" % d))
    return out


def validate(path, rules):
    """Report dict for one series file."""
    rows = problems = 0
    durum, endpoint, by_check, listed = Counter(), Counter(), Counter(), []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rows += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            found = [("json", "not valid JSON")]
            row = None
        else:
            found = check_row(row, rules)
        if isinstance(row, dict):
            durum[str(row.get("durum"))] += 1
            endpoint[str(row.get("uc"))] += 1
        if found:
            problems += 1
            for check, msg in found:
                by_check[check] += 1
                listed.append({"line": n, "check": check, "message": msg})
    return {"series": str(path), "rows": rows, "rows_failing": problems,
            "per_durum": dict(sorted(durum.items())), "per_endpoint": dict(sorted(endpoint.items())),
            "problems_per_check": dict(sorted(by_check.items())), "problems": listed}


def _text(r, limit):
    print("series: %s" % r["series"])
    print("rows: %d" % r["rows"])
    print("per durum:")
    for k, v in r["per_durum"].items():
        print("  %-28s %6d" % (k, v))
    print("per endpoint:")
    for k, v in r["per_endpoint"].items():
        print("  %-28s %6d" % (k, v))
    if not r["rows_failing"]:
        print("OK: every row passes the structural checks")
        return
    print("FAIL: %d of %d rows fail a check (%s)" % (
        r["rows_failing"], r["rows"], ", ".join("%s=%d" % kv for kv in r["problems_per_check"].items())))
    for p in r["problems"][:limit]:
        print("  line %d: [%s] %s" % (p["line"], p["check"], p["message"]))
    if len(r["problems"]) > limit:
        print("  ... %d more (use --max-problems or --json)" % (len(r["problems"]) - limit))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Check every row of an AI Supply Index series file: envelope keys and types from "
                    "the README Schema section (schema_map.json), a zaman_utc that parses as an ISO "
                    "time, an endpoint (uc) that appears in schema_map.json, and a known durum value. "
                    "Prints counts per durum and per endpoint. Exit code: 0 = every row passes, "
                    "1 = at least one row fails a check, 2 = a file cannot be read.")
    ap.add_argument("--series", default=str(DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--schema-map", dest="schema_map", default=str(DEFAULT_MAP),
                    help="path to schema_map.json (default: the one in the repository)")
    ap.add_argument("--max-problems", dest="limit", type=int, default=20,
                    help="how many problems to list in the text report (default: 20)")
    ap.add_argument("--json", action="store_true", help="print the full report as one JSON object")
    a = ap.parse_args(argv)

    try:
        report = validate(a.series, Rules(a.schema_map))
    except (OSError, ValueError, KeyError, StopIteration) as e:
        print("error: %s" % (e or type(e).__name__), file=sys.stderr)
        return 2
    try:
        if a.json:
            print(json.dumps(report, ensure_ascii=False, indent=1))
        else:
            _text(report, a.limit)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 1 if report["rows_failing"] else 0


if __name__ == "__main__":
    sys.exit(main())
