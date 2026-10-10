#!/usr/bin/env python3
"""runs.py — every collection run in the series, and which of them the weekly values come from.

One run is all rows that share a `zaman_utc` (README, "Using the series"). Some days carry more
than one run and some rows are incomplete, so the weekly tools pick one row per endpoint and
ISO week. This lists, for every run:

  week       its ISO week
  rows       how many rows (endpoints) it wrote; ok = rows with durum OK
  usable     rows that pass the README rules and have a readable value
  picked     endpoints whose weekly value comes from this run (as examples/weekly_series.py picks)
  versions   collector version(s) (surum) on its rows; toplayici when rows carry it
  unusable   for every row that is not usable, why:
               durum <value>                    the row's status is not OK
               no summary                       ozet is missing or not an object
               olculemedi: <reason>             the collector marked the summary unmeasurable
               package <name>: hata|olculemedi  a per-package sub-summary is incomplete
               no readable value                the endpoint's value cannot be read

The selection is reused from weekly_series.py by import; nothing is re-implemented.

Standard library only. Usage:
    python3 examples/runs.py
    python3 examples/runs.py --week 2026-W36
    python3 examples/runs.py --csv > runs.csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

COLUMNS = ["zaman_utc", "week", "rows", "ok", "usable", "picked", "versions", "collectors", "unusable"]


def why_unusable(row):
    """None when the row is usable and has a readable value, else a short reason."""
    if row.get("durum") != "OK":
        return "durum %s" % row.get("durum")
    ozet = row.get("ozet")
    if not isinstance(ozet, dict):
        return "no summary"
    if "olculemedi" in ozet:
        return "olculemedi: %s" % ozet["olculemedi"]
    for name, sub in sorted(ozet.items()):
        if isinstance(sub, dict):
            for mark in ("hata", "olculemedi"):
                if mark in sub:
                    return "package %s: %s" % (name, mark)
    if weekly_series.value(row) is None:
        return "no readable value"
    return None


def runs(rows):
    """One dict per run (sorted by zaman_utc) with the COLUMNS fields; list fields are lists."""
    rows = [r for r in rows if isinstance(r.get("zaman_utc"), str) and isinstance(r.get("uc"), str)]
    picked = {}
    for e in weekly_series.weekly(rows):
        if e["value"] is not None:
            picked.setdefault(e["zaman_utc"], []).append(e["endpoint"])
    by_run = {}
    for r in rows:
        by_run.setdefault(r["zaman_utc"], []).append(r)
    out = []
    for stamp in sorted(by_run):
        group = by_run[stamp]
        unusable = sorted((r["uc"], why_unusable(r)) for r in group if why_unusable(r) is not None)
        out.append({
            "zaman_utc": stamp,
            "week": weekly_series.iso_week(stamp),
            "rows": len(group),
            "ok": sum(1 for r in group if r.get("durum") == "OK"),
            "usable": len(group) - len(unusable),
            "picked": sorted(picked.get(stamp, [])),
            "versions": sorted({str(r["surum"]) for r in group if "surum" in r}),
            "collectors": sorted({str(r["toplayici"]) for r in group if "toplayici" in r}),
            "unusable": [{"endpoint": uc, "reason": why} for uc, why in unusable],
        })
    return out


def write_csv(entries, out):
    """CSV with COLUMNS; list fields are joined with ';', unusable as endpoint=reason."""
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for e in entries:
        w.writerow([e["zaman_utc"], e["week"], e["rows"], e["ok"], e["usable"], ";".join(e["picked"]),
                    ";".join(e["versions"]), ";".join(e["collectors"]),
                    ";".join("%s=%s" % (u["endpoint"], u["reason"]) for u in e["unusable"])])


def _text(entries):
    for e in entries:
        version = ",".join(e["versions"]) or "-"
        print("%s  %s  rows %2d  ok %2d  usable %2d  picked %2d  version %s%s" % (
            e["zaman_utc"], e["week"], e["rows"], e["ok"], e["usable"], len(e["picked"]), version,
            ("  collector " + ",".join(e["collectors"])) if e["collectors"] else ""))
        for u in e["unusable"]:
            print("    %-28s %s" % (u["endpoint"], u["reason"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="List every collection run in the AI Supply Index series (all rows sharing a "
                    "zaman_utc): rows, ok and usable rows, which endpoints' weekly values come from "
                    "it (as examples/weekly_series.py picks them), and why each unusable row is "
                    "unusable.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--week", action="append", metavar="YYYY-Www",
                    help="only runs in this ISO week, e.g. 2026-W36; repeat for several")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print one JSON object per run and line")
    fmt.add_argument("--csv", action="store_true", help="print CSV with the columns %s" % ",".join(COLUMNS))
    a = ap.parse_args(argv)

    try:
        entries = runs(weekly_series.read_rows(a.series))
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    if a.week:
        entries = [e for e in entries if e["week"] in a.week]
    try:
        if a.csv:
            write_csv(entries, sys.stdout)
        elif a.json:
            for e in entries:
                print(json.dumps(e, ensure_ascii=False))
        else:
            _text(entries)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
