#!/usr/bin/env python3
"""package_series.py — one value per package (or repository) and ISO week.

npm_downloads, pypi_downloads and github_repos store one sub-summary per package or repository
under `ozet` (README, "Keys that are data, not schema"). weekly_series.py sums them into one
number per endpoint; this prints them one by one, e.g. the 30-day npm downloads of
@anthropic-ai/sdk per week.

The row for each week is the one weekly_series.py picks (reused by import), so the rules from
"Using the series" in README.md apply unchanged: only usable rows; a row in which any package
carries `hata` or `olculemedi` is missing data as a whole; the last usable row of a week wins.

Missing values stay missing, never 0:
  - a week without a usable row is a gap for every package (reason from weekly_series.py);
  - a package that the chosen row does not list is a gap ("package not in this row");
  - a field that is not a number in the chosen row is a gap ("no numeric value").

Fields (default first): npm_downloads toplam_30g, gun; pypi_downloads aynasiz_toplam,
aynasiz_son30g, aynasiz_gun, kayit; github_repos yildiz, catal, izleyen, acik_konu.
See the README "Schema" section for what each field measures and over which window.

Standard library only. Usage:
    python3 examples/package_series.py --endpoint npm_downloads --package @anthropic-ai/sdk
    python3 examples/package_series.py --endpoint github_repos --field catal --csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

FIELDS = {
    "npm_downloads": ["toplam_30g", "gun"],
    "pypi_downloads": ["aynasiz_toplam", "aynasiz_son30g", "aynasiz_gun", "kayit"],
    "github_repos": ["yildiz", "catal", "izleyen", "acik_konu"],
}
COLUMNS = ["week", "endpoint", "package", "field", "value", "zaman_utc", "gap"]


def _number(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def packages(rows, endpoint):
    """Every package or repository name listed in any row of the endpoint, sorted."""
    found = set()
    for r in rows:
        o = r.get("ozet")
        if r.get("uc") == endpoint and isinstance(o, dict):
            found.update(k for k, v in o.items() if isinstance(v, dict))
    return sorted(found)


def package_series(rows, endpoint, field=None, only=None):
    """One entry per (week, package), sorted by week then package.

    Each entry: week, endpoint, package, field, value, zaman_utc, and `gap` (a reason) when the
    value is missing."""
    field = field or FIELDS[endpoint][0]
    names = [p for p in packages(rows, endpoint) if only is None or p in only]
    by_key = {(r.get("zaman_utc"), r.get("uc")): r for r in rows}
    out = []
    for e in weekly_series.weekly(rows, [endpoint]):
        ozet = by_key[(e["zaman_utc"], endpoint)]["ozet"] if e["value"] is not None else None
        for p in names:
            entry = {"week": e["week"], "endpoint": endpoint, "package": p, "field": field,
                     "value": None, "zaman_utc": e.get("zaman_utc")}
            if ozet is None:
                entry["gap"] = e["gap"]
            elif not isinstance(ozet.get(p), dict):
                entry["gap"] = "package not in this row"
            else:
                entry["value"] = _number(ozet[p].get(field))
                if entry["value"] is None:
                    entry["gap"] = "no numeric value"
            out.append(entry)
    out.sort(key=lambda x: (x["week"], x["package"]))
    return out


def write_csv(entries, out):
    """CSV with COLUMNS; a missing value is an empty cell, never 0."""
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for e in entries:
        w.writerow(["" if e.get(c) is None else (repr(e[c]) if c == "value" else e[c]) for c in COLUMNS])


def _text(entries):
    width = max([len(e["package"]) for e in entries] + [7])
    for e in entries:
        if e["value"] is None:
            print("%s  %-*s  GAP (%s)" % (e["week"], width, e["package"], e["gap"]))
        else:
            print("%s  %-*s  %16s  %s" % (e["week"], width, e["package"], format(e["value"], ",.10g"),
                                          e["zaman_utc"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print one value per package or repository and ISO week for npm_downloads, "
                    "pypi_downloads or github_repos, from the row examples/weekly_series.py picks "
                    "for the week. Missing values (a gap week, a package the row does not list, a "
                    "field that is not a number) are printed as GAP, never as 0.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", required=True, choices=sorted(FIELDS),
                    help="the endpoint whose packages or repositories to print")
    ap.add_argument("--field",
                    help="the per-package field to print (default: the first one listed for the "
                         "endpoint: %s)" % "; ".join("%s %s" % (k, ", ".join(v)) for k, v in sorted(FIELDS.items())))
    ap.add_argument("--package", action="append", metavar="NAME",
                    help="only this package or repository; repeat for several (default: all)")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print one JSON object per line")
    fmt.add_argument("--csv", action="store_true",
                     help="print CSV with the columns %s; missing values are empty" % ",".join(COLUMNS))
    a = ap.parse_args(argv)
    if a.field is not None and a.field not in FIELDS[a.endpoint]:
        ap.error("--field for %s must be one of: %s" % (a.endpoint, ", ".join(FIELDS[a.endpoint])))

    try:
        entries = package_series(weekly_series.read_rows(a.series), a.endpoint, a.field, a.package)
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
