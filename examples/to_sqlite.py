#!/usr/bin/env python3
"""to_sqlite.py — load an AI Supply Index series file into a SQLite database.

Two tables, written with the standard sqlite3 module:

  rows    one row per line of the series. `row_id` is the line number (1 = first line). One column
          per envelope key from the README "Record envelope" table (read from schema_map.json),
          except `ozet`; `has_ozet` says whether the line had a summary object. A key the line does
          not carry is NULL. Top-level keys outside the envelope go to `extra` as JSON (else NULL).

  leaves  one row per leaf of the summary (`ozet`): row_id, path, value, type.
          `path` is a JSON Pointer inside ozet (RFC 6901: "/" separates keys, list items are
          numbered from 0, and a "/" or "~" inside a key is written "~1" or "~0"), so
          "/@anthropic-ai~1sdk/toplam_30g" is the toplam_30g of the package "@anthropic-ai/sdk".
          `type` is one of integer, real, text, boolean, null, empty_object, empty_array.
          A JSON null, an empty object and an empty array have value NULL; nothing is ever turned
          into 0. A boolean is stored as 1 or 0 with type boolean.

The series' own rules for what is usable (README, "Using the series") are not applied here; every
line is loaded as it is, so the selection can be done in SQL. Example:

  SELECT r.zaman_utc, l.value FROM rows r JOIN leaves l USING (row_id)
  WHERE r.uc = 'x402_discovery' AND r.durum = 'OK' AND l.path = '/kaynak_sayisi';

Standard library only. Usage:
    python3 examples/to_sqlite.py --db series.sqlite
    python3 examples/to_sqlite.py --series other.ndjson --db other.sqlite --replace
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERIES = ROOT / "ai-arz-serisi.ndjson"
DEFAULT_MAP = ROOT / "schema_map.json"
SQL_TYPES = {"string": "TEXT", "number": "REAL", "integer": "INTEGER"}


def envelope_columns(map_path=DEFAULT_MAP):
    """[(key, sql type)] for the Record envelope keys in schema_map.json, without ozet."""
    m = json.loads(Path(map_path).read_text(encoding="utf-8"))
    group = next(g for g in m["groups"] if g["name"] == "Record envelope")
    return [(k, SQL_TYPES.get(t.split()[0], "TEXT")) for k, _en, t, _d in group["keys"] if k != "ozet"]


def pointer(parts):
    """JSON Pointer (RFC 6901) for a list of keys and list indices."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def leaves(node, parts=()):
    """Yield (path, value, type) for every leaf under node."""
    if isinstance(node, dict):
        if not node:
            yield pointer(parts), None, "empty_object"
        for k, v in node.items():
            yield from leaves(v, parts + (k,))
    elif isinstance(node, list):
        if not node:
            yield pointer(parts), None, "empty_array"
        for i, v in enumerate(node):
            yield from leaves(v, parts + (i,))
    elif node is None:
        yield pointer(parts), None, "null"
    elif isinstance(node, bool):
        yield pointer(parts), int(node), "boolean"
    elif isinstance(node, int):
        yield pointer(parts), node, "integer"
    elif isinstance(node, float):
        yield pointer(parts), node, "real"
    else:
        yield pointer(parts), str(node), "text"


def _q(name):
    return '"%s"' % name.replace('"', '""')


def load(series, db, map_path=DEFAULT_MAP):
    """Write the two tables into the sqlite3 connection `db`. Returns (rows, leaves) counts."""
    cols = envelope_columns(map_path)
    names = [k for k, _ in cols]
    db.execute("CREATE TABLE rows (row_id INTEGER PRIMARY KEY, %s, has_ozet INTEGER NOT NULL, extra TEXT)"
               % ", ".join("%s %s" % (_q(k), t) for k, t in cols))
    db.execute("CREATE TABLE leaves (row_id INTEGER NOT NULL REFERENCES rows(row_id), path TEXT NOT NULL, "
               "value, type TEXT NOT NULL)")
    db.execute("CREATE INDEX leaves_path ON leaves(path)")
    n_rows = n_leaves = 0
    for n, line in enumerate(Path(series).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError("line %d is not valid JSON: %s" % (n, e)) from None
        if not isinstance(row, dict):
            raise ValueError("line %d is not a JSON object" % n)
        values = []
        for k in names:
            v = row.get(k)
            values.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
        extra = {k: v for k, v in row.items() if k not in names and k != "ozet"}
        ozet = row.get("ozet")
        db.execute("INSERT INTO rows VALUES (?, %s, ?, ?)" % ", ".join("?" * len(names)),
                   [n] + values + [int(isinstance(ozet, dict)), json.dumps(extra, ensure_ascii=False) if extra else None])
        n_rows += 1
        if "ozet" in row:
            batch = [(n, p, v, t) for p, v, t in leaves(ozet)]
            db.executemany("INSERT INTO leaves VALUES (?, ?, ?, ?)", batch)
            n_leaves += len(batch)
    db.commit()
    return n_rows, n_leaves


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Load an AI Supply Index series file into SQLite: a 'rows' table with the Record "
                    "envelope keys (one row per line) and a 'leaves' table with every leaf of the "
                    "summary as (row_id, JSON Pointer path, value, type). Missing values are NULL, "
                    "never 0.")
    ap.add_argument("--series", default=str(DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--db", required=True, help="the SQLite file to write")
    ap.add_argument("--replace", action="store_true", help="overwrite the database file if it exists")
    ap.add_argument("--schema-map", dest="schema_map", default=str(DEFAULT_MAP),
                    help="path to schema_map.json, which lists the envelope keys (default: the repository's)")
    a = ap.parse_args(argv)

    target = Path(a.db)
    if target.exists():
        if not a.replace:
            print("error: %s exists; use --replace to overwrite it" % target, file=sys.stderr)
            return 1
        target.unlink()
    db = sqlite3.connect(target)
    try:
        n_rows, n_leaves = load(a.series, db, a.schema_map)
    except (OSError, ValueError, KeyError, StopIteration) as e:
        db.close()
        target.unlink(missing_ok=True)
        print("error: %s" % (e or type(e).__name__), file=sys.stderr)
        return 1
    db.close()
    print("written: %s (%d rows, %d leaves)" % (target, n_rows, n_leaves))
    return 0


if __name__ == "__main__":
    sys.exit(main())
