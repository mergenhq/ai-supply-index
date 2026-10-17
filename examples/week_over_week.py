#!/usr/bin/env python3
"""week_over_week.py — per endpoint, the change between consecutive ISO weeks.

Built on weekly_series.py: the weekly values come from its weekly(), so the rules are the same
as in "Using the series" in README.md (only usable rows; olculemedi and per-package hata or
olculemedi are missing data; the last usable row of a week wins).

For each endpoint and each pair of consecutive weeks it prints the absolute change, and the
percentage change when the earlier value is not 0. If either week is a gap, the pair is a gap:
there is never a change from or to 0 in place of missing data.

Standard library only. Usage:
    python3 examples/week_over_week.py
    python3 examples/week_over_week.py --endpoint apify_store --json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)


def changes(entries):
    """Pairs of consecutive weeks per endpoint, from weekly_series.weekly() entries.

    Each result: {"endpoint", "week", "previous_week", "previous", "value", "change",
    "change_pct"} where change_pct is None when previous is 0; or, when either week has no
    value, {"endpoint", "week", "previous_week", "previous", "value", "change": None,
    "change_pct": None, "gap": reason}."""
    by_endpoint = {}
    for e in entries:
        by_endpoint.setdefault(e["endpoint"], []).append(e)
    out = []
    for name in sorted(by_endpoint):
        weeks = sorted(by_endpoint[name], key=lambda e: e["week"])
        for before, after in zip(weeks, weeks[1:]):
            r = {"endpoint": name, "week": after["week"], "previous_week": before["week"],
                 "previous": before["value"], "value": after["value"]}
            missing = [e["week"] for e in (before, after) if e["value"] is None]
            if missing:
                r.update(change=None, change_pct=None, gap="no usable value in " + " and ".join(missing))
            else:
                d = after["value"] - before["value"]
                r["change"] = round(d, 4) if isinstance(d, float) else d   # floats: no binary noise
                r["change_pct"] = (None if before["value"] == 0
                                   else round(100.0 * r["change"] / abs(before["value"]), 4))
            out.append(r)
    out.sort(key=lambda r: (r["week"], r["endpoint"]))
    return out


def _fmt(v):
    return format(v, ",.10g")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print, per endpoint, the change between consecutive ISO weeks of the AI Supply "
                    "Index series: absolute, and in percent when the earlier value is not 0. Weekly "
                    "values follow the same rules as examples/weekly_series.py. If either week has no "
                    "usable value the pair is printed as GAP, never as a change from or to 0.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", action="append", choices=sorted(weekly_series.VALUES), metavar="NAME",
                    help="only this endpoint; repeat for several (default: every endpoint in the series)")
    ap.add_argument("--json", action="store_true", help="print one JSON object per line instead of a table")
    a = ap.parse_args(argv)

    try:
        rows = changes(weekly_series.weekly(weekly_series.read_rows(a.series), a.endpoint))
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1

    try:
        for r in rows:
            if a.json:
                print(json.dumps(r, ensure_ascii=False))
            elif r["change"] is None:
                print("%s  %-28s  GAP (%s)" % (r["week"], r["endpoint"], r["gap"]))
            else:
                pct = "n/a (from 0)" if r["change_pct"] is None else "%+.2f %%" % r["change_pct"]
                print("%s  %-28s  %-18s  %-14s  (%s -> %s)" % (
                    r["week"], r["endpoint"], format(r["change"], "+,.10g"), pct,
                    _fmt(r["previous"]), _fmt(r["value"])))
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
