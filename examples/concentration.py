#!/usr/bin/env python3
"""concentration.py — distribution summaries per endpoint, field and ISO week.

Several endpoints archive whole distributions, not only totals (README, "Distribution summary"):
x402_discovery cagri_30g and odeyen_30g, sherlock_leaderboard omur_boyu_odeme, apify_store
toplam_kullanici_dagilimi, hf_models indirme_dagilimi, defillama_fees_ai_agents ai_30g_dagilim and
defillama_summary_virtuals son30g_dagilim. A distribution field is any object in `ozet` that carries
`n` and `p50` in at least one row; in other rows the same field may be {"n": 0} (empty).

For every endpoint, distribution field and ISO week this prints n, p50, p90, top1_pay and top10_pay
from the row that examples/weekly_series.py picks for that week (same rules: only usable rows;
olculemedi and per-package hata or olculemedi are missing data; the last usable row of a week
wins). The selection is reused by import, not copied.

Missing values stay missing, never 0:
  - a week without a usable row is a gap (the reason comes from weekly_series.py);
  - a field that the chosen row does not carry is a gap ("field not in this row");
  - top1_pay and top10_pay are absent when the distribution total is 0, and p50/p90 are absent
    when n is 0; they are printed as empty.

Standard library only. Usage:
    python3 examples/concentration.py --endpoint x402_discovery
    python3 examples/concentration.py --csv > concentration.csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

STATS = ["n", "p50", "p90", "top1_pay", "top10_pay"]
COLUMNS = ["week", "endpoint", "field"] + STATS + ["zaman_utc", "gap"]


def is_distribution(v):
    """True for an object written by the collector's dagilim_ozeti()."""
    return isinstance(v, dict) and "n" in v and "p50" in v


def distribution_fields(rows):
    """{endpoint: sorted field names} over every row that carries a distribution field."""
    found = {}
    for r in rows:
        o = r.get("ozet")
        if isinstance(o, dict) and isinstance(r.get("uc"), str):
            for k, v in o.items():
                if is_distribution(v):
                    found.setdefault(r["uc"], set()).add(k)
    return {uc: sorted(ks) for uc, ks in found.items()}


def concentration(rows, endpoints=None):
    """One entry per (week, endpoint, field), sorted by week, endpoint and field.

    Each entry has week, endpoint, field, the STATS keys (None when absent), zaman_utc of the chosen
    row, and `gap` (a reason) when the week has no usable row or the row lacks the field."""
    fields = distribution_fields(rows)
    if endpoints is not None:
        fields = {uc: f for uc, f in fields.items() if uc in endpoints}
    by_key = {(r.get("zaman_utc"), r.get("uc")): r for r in rows}
    out = []
    for e in weekly_series.weekly(rows, sorted(fields)):
        for field in fields.get(e["endpoint"], []):
            entry = {"week": e["week"], "endpoint": e["endpoint"], "field": field}
            entry.update({s: None for s in STATS})
            if e["value"] is None:
                entry.update(zaman_utc=None, gap=e["gap"])
            else:
                d = by_key[(e["zaman_utc"], e["endpoint"])]["ozet"].get(field)
                entry["zaman_utc"] = e["zaman_utc"]
                if isinstance(d, dict) and "n" in d:      # {"n": 0} is an empty distribution
                    for s in STATS:
                        v = d.get(s)
                        entry[s] = v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
                else:
                    entry["gap"] = "field not in this row"
            out.append(entry)
    out.sort(key=lambda x: (x["week"], x["endpoint"], x["field"]))
    return out


def write_csv(entries, out):
    """CSV with COLUMNS; a missing value is an empty cell, never 0."""
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for e in entries:
        w.writerow(["" if e.get(c) is None else (repr(e[c]) if c in STATS else e[c]) for c in COLUMNS])


def _cell(v, fmt):
    return "" if v is None else format(v, fmt)


def _text(entries):
    print("%-8s  %-26s  %-26s  %8s  %12s  %12s  %8s  %9s" % (
        "week", "endpoint", "field", "n", "p50", "p90", "top1", "top10"))
    for e in entries:
        if e.get("gap"):
            print("%-8s  %-26s  %-26s  GAP (%s)" % (e["week"], e["endpoint"], e["field"], e["gap"]))
            continue
        print("%-8s  %-26s  %-26s  %8s  %12s  %12s  %8s  %9s" % (
            e["week"], e["endpoint"], e["field"], _cell(e["n"], ",d"), _cell(e["p50"], ",.6g"),
            _cell(e["p90"], ",.6g"), _cell(e["top1_pay"], ".4f"), _cell(e["top10_pay"], ".4f")))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print n, p50, p90, top1_pay and top10_pay of every distribution field per "
                    "endpoint and ISO week of the AI Supply Index series, from the row that "
                    "examples/weekly_series.py picks for the week. Missing values (a gap week, a "
                    "field the row does not carry, top shares when the total is 0) are empty, "
                    "never 0.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", action="append", choices=sorted(weekly_series.VALUES), metavar="NAME",
                    help="only this endpoint; repeat for several (default: every endpoint that has a "
                         "distribution field)")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print one JSON object per line")
    fmt.add_argument("--csv", action="store_true",
                     help="print CSV with the columns %s; missing values are empty" % ",".join(COLUMNS))
    a = ap.parse_args(argv)

    try:
        entries = concentration(weekly_series.read_rows(a.series), a.endpoint)
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
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
