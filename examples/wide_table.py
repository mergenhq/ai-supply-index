#!/usr/bin/env python3
"""wide_table.py — the AI Supply Index series as one CSV row per ISO week and one column per endpoint.

Built on weekly_series.py: the weekly values come from its weekly(), so the selection rules are
the same as in "Using the series" in README.md (only usable rows; olculemedi and per-package
hata or olculemedi are missing data; the last usable row of a week wins).

The first column is the ISO week; there is one row for every week from the first to the last
week in the series. Every other column is an endpoint, in name order. A week without a usable
value for an endpoint, including weeks before its first row, is an empty cell, never 0.

Standard library only. Usage:
    python3 examples/wide_table.py > wide.csv
    python3 examples/wide_table.py --endpoint x402_discovery --endpoint apify_store
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)


def wide(entries):
    """(header, rows) from weekly_series.weekly() entries. Missing values are None."""
    if not entries:
        return ["week"], []
    names = sorted({e["endpoint"] for e in entries})
    weeks = [e["week"] for e in entries]
    cells = {(e["week"], e["endpoint"]): e["value"] for e in entries}
    rows = [[w] + [cells.get((w, n)) for n in names]
            for w in weekly_series._weeks(min(weeks), max(weeks))]
    return ["week"] + names, rows


def write_csv(header, rows, out):
    """CSV; a missing value is an empty cell."""
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r[0]] + ["" if v is None else repr(v) for v in r[1:]])


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Write the AI Supply Index series as CSV with one row per ISO week and one "
                    "column per endpoint. Rows are selected as in examples/weekly_series.py; a week "
                    "without a usable value is an empty cell, never 0.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", action="append", choices=sorted(weekly_series.VALUES), metavar="NAME",
                    help="only this endpoint as a column; repeat for several (default: every endpoint "
                         "in the series)")
    a = ap.parse_args(argv)

    try:
        header, rows = wide(weekly_series.weekly(weekly_series.read_rows(a.series), a.endpoint))
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    try:
        write_csv(header, rows, sys.stdout)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
