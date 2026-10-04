#!/usr/bin/env python3
"""endpoint_summary.py — one summary line per endpoint of the AI Supply Index series.

Built on weekly_series.py: the weekly values come from its weekly(), so the selection rules are
the same as in "Using the series" in README.md (only usable rows; olculemedi and per-package
hata or olculemedi are missing data; the last usable row of a week wins).

For each endpoint it reports:
  first_week, last_week   first and last ISO week with a usable value
  usable_weeks            how many weeks have a usable value
  gap_weeks               weeks without a usable value between first_week and last_week
  latest_value            the value in last_week, with the zaman_utc of the row it came from
An endpoint that has rows but no usable value has usable_weeks 0 and empty weeks and value.

Standard library only. Usage:
    python3 examples/endpoint_summary.py
    python3 examples/endpoint_summary.py --json
    python3 examples/endpoint_summary.py --csv > summary.csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

COLUMNS = ["endpoint", "first_week", "last_week", "usable_weeks", "gap_weeks",
           "latest_value", "latest_zaman_utc"]


def summarise(entries):
    """One dict per endpoint (sorted by name) from weekly_series.weekly() entries."""
    by_endpoint = {}
    for e in entries:
        by_endpoint.setdefault(e["endpoint"], []).append(e)
    out = []
    for name in sorted(by_endpoint):
        weeks = sorted(by_endpoint[name], key=lambda e: e["week"])
        usable = [e for e in weeks if e["value"] is not None]
        s = {"endpoint": name, "first_week": None, "last_week": None, "usable_weeks": len(usable),
             "gap_weeks": 0, "latest_value": None, "latest_zaman_utc": None}
        if usable:
            first, last = usable[0]["week"], usable[-1]["week"]
            s.update(first_week=first, last_week=last,
                     gap_weeks=sum(1 for e in weeks if first < e["week"] < last and e["value"] is None),
                     latest_value=usable[-1]["value"], latest_zaman_utc=usable[-1]["zaman_utc"])
        out.append(s)
    return out


def write_csv(rows, out):
    """CSV with COLUMNS; a missing week or value is an empty field, never 0."""
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow(["" if r[c] is None else (repr(r[c]) if c == "latest_value" else r[c]) for c in COLUMNS])


def _text(rows):
    for r in rows:
        if not r["usable_weeks"]:
            print("%-28s  no usable value" % r["endpoint"])
            continue
        print("%-28s  %s .. %s  %3d usable  %3d gap  latest %s (%s)" % (
            r["endpoint"], r["first_week"], r["last_week"], r["usable_weeks"], r["gap_weeks"],
            format(r["latest_value"], ",.10g"), r["latest_zaman_utc"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print one summary per endpoint of the AI Supply Index series: first and last "
                    "ISO week with a usable value, number of usable weeks, number of gap weeks "
                    "between them, and the latest value. Rows are selected as in "
                    "examples/weekly_series.py; missing data is never counted as zero.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", action="append", choices=sorted(weekly_series.VALUES), metavar="NAME",
                    help="only this endpoint; repeat for several (default: every endpoint in the series)")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print one JSON object per endpoint and line")
    fmt.add_argument("--csv", action="store_true",
                     help="print CSV with the columns %s; missing fields are empty" % ",".join(COLUMNS))
    a = ap.parse_args(argv)

    try:
        rows = summarise(weekly_series.weekly(weekly_series.read_rows(a.series), a.endpoint))
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1

    try:
        if a.csv:
            write_csv(rows, sys.stdout)
        elif a.json:
            for r in rows:
                print(json.dumps(r, ensure_ascii=False))
        else:
            _text(rows)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
