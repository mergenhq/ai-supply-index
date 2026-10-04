#!/usr/bin/env python3
"""histogram.py — the histogram of one distribution field, week by week.

Several endpoints archive whole distributions (README, "Distribution summary"); each one carries a
`histogram` object of bucket label -> count, e.g. x402_discovery cagri_30g:
{"<1": 8, "1-10": 16343, "10-100": 1166, ...}. A bucket "a-b" holds the values v with a <= v < b,
"<a" the values below a, ">=b" the values from b up (the collector writes them that way).

For every ISO week this prints each bucket's count and its share of n (count / n), from the row
that examples/weekly_series.py picks for the week (reused by import, so the README selection rules
apply unchanged). Buckets keep the order in which the series stores them.

Missing values stay missing, never 0:
  - a week without a usable row is a gap (reason from weekly_series.py);
  - a chosen row without the field, or with a field that has no histogram, is a gap;
  - an empty distribution ({"n": 0}) is printed as such, with no buckets.

Standard library only. Usage:
    python3 examples/histogram.py --endpoint x402_discovery
    python3 examples/histogram.py --endpoint x402_discovery --field odeyen_30g --csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

COLUMNS = ["week", "endpoint", "field", "bucket", "count", "share", "n", "zaman_utc", "gap"]


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def histogram_fields(rows, endpoint):
    """Fields of the endpoint's summaries that carry a histogram object, sorted."""
    found = set()
    for r in rows:
        o = r.get("ozet")
        if r.get("uc") == endpoint and isinstance(o, dict):
            found.update(k for k, v in o.items() if isinstance(v, dict) and isinstance(v.get("histogram"), dict))
    return sorted(found)


def histogram(rows, endpoint, field):
    """One dict per week: week, endpoint, field, n, zaman_utc, buckets [(label, count, share)],
    and `gap` (a reason) when the week has no histogram to show."""
    by_key = {(r.get("zaman_utc"), r.get("uc")): r for r in rows}
    out = []
    for e in weekly_series.weekly(rows, [endpoint]):
        week = {"week": e["week"], "endpoint": endpoint, "field": field, "n": None, "zaman_utc": None,
                "buckets": []}
        if e["value"] is None:
            week["gap"] = e["gap"]
            out.append(week)
            continue
        week["zaman_utc"] = e["zaman_utc"]
        d = by_key[(e["zaman_utc"], endpoint)]["ozet"].get(field)
        if not isinstance(d, dict) or "n" not in d:
            week["gap"] = "field not in this row"
        else:
            week["n"] = _int(d.get("n"))
            h = d.get("histogram")
            if isinstance(h, dict):
                for label, count in h.items():
                    count = _int(count)
                    share = round(count / week["n"], 6) if count is not None and week["n"] else None
                    week["buckets"].append((label, count, share))
            elif week["n"] != 0:
                week["gap"] = "no histogram in this field"
        out.append(week)
    return out


def write_csv(weeks, out):
    """One CSV row per bucket, or one row per week without buckets; missing values are empty."""
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for wk in weeks:
        base = [wk["week"], wk["endpoint"], wk["field"]]
        tail = ["" if wk["n"] is None else wk["n"], wk["zaman_utc"] or "", wk.get("gap", "")]
        if not wk["buckets"]:
            w.writerow(base + ["", "", ""] + tail)
        for label, count, share in wk["buckets"]:
            w.writerow(base + [label, "" if count is None else count, "" if share is None else repr(share)] + tail)


def _text(weeks, width=40):
    if weeks:
        print("%s %s: bucket counts and share of n per ISO week" % (weeks[0]["endpoint"], weeks[0]["field"]))
    for wk in weeks:
        if wk.get("gap"):
            print("%s  GAP (%s)" % (wk["week"], wk["gap"]))
            continue
        if not wk["buckets"]:
            print("%s  n=%s  empty distribution" % (wk["week"], wk["n"]))
            continue
        print("%s  n=%s  (%s)" % (wk["week"], format(wk["n"], ","), wk["zaman_utc"]))
        for label, count, share in wk["buckets"]:
            bar = "#" * int(round((share or 0) * width))
            print("    %-14s %10s  %7s  %s" % (label, "" if count is None else format(count, ","),
                                               "" if share is None else "%.1f%%" % (share * 100), bar))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print the histogram of one distribution field per ISO week: each bucket's count "
                    "and share of n, from the row examples/weekly_series.py picks for the week. A gap "
                    "week or a missing field is printed as GAP, never as 0.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", required=True, choices=sorted(weekly_series.VALUES), metavar="NAME",
                    help="the endpoint (one with a distribution: x402_discovery, sherlock_leaderboard, "
                         "apify_store, hf_models, defillama_fees_ai_agents, defillama_summary_virtuals)")
    ap.add_argument("--field", help="the distribution field (default: the first one the endpoint has, by name)")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print one JSON object per week and line")
    fmt.add_argument("--csv", action="store_true",
                     help="print CSV with the columns %s; one row per bucket, missing values empty" % ",".join(COLUMNS))
    a = ap.parse_args(argv)

    try:
        rows = weekly_series.read_rows(a.series)
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    fields = histogram_fields(rows, a.endpoint)
    if not fields:
        print("error: %s has no distribution field with a histogram in this series" % a.endpoint, file=sys.stderr)
        return 1
    field = a.field or fields[0]
    if field not in fields:
        print("error: %s has no distribution field %r; it has: %s" % (a.endpoint, field, ", ".join(fields)),
              file=sys.stderr)
        return 1
    weeks = histogram(rows, a.endpoint, field)
    try:
        if a.csv:
            write_csv(weeks, sys.stdout)
        elif a.json:
            for wk in weeks:
                print(json.dumps(dict(wk, buckets=[{"bucket": b, "count": c, "share": s} for b, c, s in wk["buckets"]]),
                                 ensure_ascii=False))
        else:
            _text(weeks)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
