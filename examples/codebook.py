#!/usr/bin/env python3
"""codebook.py — schema_map.json as a CSV codebook for spreadsheets and statistics tools.

schema_map.json is the key contract of the series (the README "Schema" tables are generated from
it). This writes it as CSV with one row per key, in the order of the file:

  section       "passthrough" for the two passthrough rules, "key" for every mapped key
  group         the passthrough rule name, or the group the key belongs to
  key           the key as stored in ai-arz-serisi.ndjson (for a passthrough rule: what kind of
                runtime value appears there)
  english_key   the key in series-en.ndjson (for a passthrough rule: the same, copied unchanged)
  type          the type text from schema_map.json
  description   the description from schema_map.json, unescaped (a "|" stays a "|")

The passthrough rows come first because they come first in schema_map.json; their description
lists the endpoints and examples the rule applies to.

Standard library only. Usage:
    python3 examples/codebook.py > codebook.csv
    python3 examples/codebook.py --out codebook.csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

DEFAULT_MAP = Path(__file__).resolve().parent.parent / "schema_map.json"
COLUMNS = ["section", "group", "key", "english_key", "type", "description"]

# what a passthrough rule's keys are, in words (the rules themselves have no single key)
_PASSTHROUGH_KEY = {"histogram_buckets": "<histogram bucket label>",
                    "package_identifiers": "<package or repository identifier>"}


def codebook(schema_map):
    """List of row dicts (COLUMNS) from a loaded schema_map.json, in file order."""
    rows = []
    for name, rule in schema_map.get("passthrough", {}).items():
        desc = rule["rule"]
        if rule.get("endpoints"):
            desc += " Endpoints: %s." % ", ".join(rule["endpoints"])
        if rule.get("examples"):
            desc += " Examples: %s." % ", ".join(rule["examples"])
        key = _PASSTHROUGH_KEY.get(name, "<%s>" % name)
        rows.append({"section": "passthrough", "group": name, "key": key, "english_key": key,
                     "type": "data (copied unchanged)", "description": desc})
    for g in schema_map["groups"]:
        for tr, en, typ, desc in g["keys"]:
            rows.append({"section": "key", "group": g["name"], "key": tr, "english_key": en,
                         "type": typ, "description": desc})
    return rows


def write_csv(rows, out):
    w = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Write schema_map.json as a CSV codebook: one row per key in file order, with "
                    "the columns %s. The two passthrough rules are rows with section "
                    "'passthrough'." % ", ".join(COLUMNS))
    ap.add_argument("--schema-map", dest="schema_map", default=str(DEFAULT_MAP),
                    help="path to schema_map.json (default: the one in the repository)")
    ap.add_argument("--out", default="-", help="file to write the CSV to (default: standard output)")
    a = ap.parse_args(argv)

    try:
        rows = codebook(json.loads(Path(a.schema_map).read_text(encoding="utf-8")))
        if a.out == "-":
            write_csv(rows, sys.stdout)
        else:
            with open(a.out, "w", encoding="utf-8", newline="") as f:
                write_csv(rows, f)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    except (OSError, ValueError, KeyError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
