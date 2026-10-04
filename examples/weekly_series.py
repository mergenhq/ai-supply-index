#!/usr/bin/env python3
"""weekly_series.py — one value per endpoint and ISO week, following "Using the series" in README.md.

Rules (the same as the README):
  - only rows with durum == "OK" are used;
  - a summary that carries `olculemedi`, or a per-package sub-summary that carries `hata` or
    `olculemedi`, is missing data — never a measured zero;
  - per endpoint and ISO week, the last usable row wins (latest zaman_utc).

The value printed for each endpoint is its load-bearing number (see VALUES below). A usable row
whose value cannot be read is also treated as missing. A week with no usable row for an endpoint
is printed as a GAP, from the endpoint's first row to the last week in the series.

Standard library only. Usage:
    python3 examples/weekly_series.py
    python3 examples/weekly_series.py --endpoint x402_discovery --json
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_SERIES = Path(__file__).resolve().parent.parent / "ai-arz-serisi.ndjson"


def _path(*keys):
    def read(summary):
        v = summary
        for k in keys:
            v = v.get(k) if isinstance(v, dict) else None
        return v
    return read


def _sum_over_packages(key):
    """npm/pypi/github summaries hold one sub-summary per package or repository."""
    def read(summary):
        values = [v.get(key) for v in summary.values() if isinstance(v, dict)]
        values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return sum(values) if values else None
    return read


# endpoint -> (what the value is, how to read it from `ozet`)
VALUES = {
    "x402_discovery":             ("resources registered", _path("kaynak_sayisi")),
    "sherlock_leaderboard":       ("researchers listed", _path("arastirmaci_sayisi")),
    "sherlock_contests":          ("contests open now", _path("acik_yarisma")),
    "code4rena_audits":           ("audits open now", _path("acik_yarisma")),
    "defillama_fees_ai_agents":   ("AI-agent fees, 30d (USD)", _path("ai_total30d")),
    "defillama_summary_virtuals": ("protocol fees, 30d (USD)", _path("total30d")),
    "apify_store":                ("actors in the store", _path("magaza_toplam_aktor")),
    "hf_models":                  ("downloads, top 100 models", _path("indirme_dagilimi", "toplam")),
    "npm_downloads":              ("downloads, 30d, all packages", _sum_over_packages("toplam_30g")),
    "pypi_downloads":             ("non-mirror downloads, all packages", _sum_over_packages("aynasiz_toplam")),
    "github_repos":               ("stars, all repositories", _sum_over_packages("yildiz")),
}


def read_rows(path):
    """Every non-blank line as a dict. A line that is not a JSON object stops the run."""
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError("line %d is not valid JSON: %s" % (n, e)) from None
        if not isinstance(row, dict):
            raise ValueError("line %d is not a JSON object" % n)
        rows.append(row)
    return rows


def usable(row):
    """The README rules: OK status, no olculemedi, no per-package hata or olculemedi."""
    summary = row.get("ozet")
    if row.get("durum") != "OK" or not isinstance(summary, dict) or "olculemedi" in summary:
        return False
    return not any(isinstance(v, dict) and ("hata" in v or "olculemedi" in v) for v in summary.values())


def value(row):
    """The endpoint's value, or None when the row is not usable or the value cannot be read."""
    if not usable(row) or row.get("uc") not in VALUES:
        return None
    v = VALUES[row["uc"]][1](row["ozet"])
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def iso_week(stamp):
    year, week, _ = datetime.fromisoformat(stamp.replace("Z", "+00:00")).isocalendar()
    return "%d-W%02d" % (year, week)


def _weeks(first, last):
    """ISO week labels from `first` to `last` inclusive."""
    y, w = (int(x) for x in first.split("-W"))
    day = date.fromisocalendar(y, w, 1)
    out = []
    while True:
        label = "%d-W%02d" % day.isocalendar()[:2]
        out.append(label)
        if label == last:
            return out
        day += timedelta(days=7)


def weekly(rows, endpoints=None):
    """One entry per (week, endpoint), sorted by week then endpoint.

    Each entry: {"week", "endpoint", "value", "zaman_utc"} for a usable row, or
    {"week", "endpoint", "value": None, "gap": reason} when the week has no usable row."""
    rows = [r for r in rows if isinstance(r.get("zaman_utc"), str) and isinstance(r.get("uc"), str)]
    if not rows:
        return []
    names = sorted(endpoints if endpoints is not None else {r["uc"] for r in rows if r["uc"] in VALUES})
    last_week = max(iso_week(r["zaman_utc"]) for r in rows)

    best, seen = {}, set()
    for r in rows:
        key = (iso_week(r["zaman_utc"]), r["uc"])
        seen.add(key)
        if value(r) is None:
            continue
        if key not in best or r["zaman_utc"] > best[key]["zaman_utc"]:
            best[key] = r

    out = []
    for name in names:
        own = [iso_week(r["zaman_utc"]) for r in rows if r["uc"] == name]
        if not own:
            continue
        for week in _weeks(min(own), last_week):
            r = best.get((week, name))
            if r is not None:
                out.append({"week": week, "endpoint": name, "value": value(r), "zaman_utc": r["zaman_utc"]})
            else:
                reason = "rows present, none usable" if (week, name) in seen else "no rows"
                out.append({"week": week, "endpoint": name, "value": None, "gap": reason})
    out.sort(key=lambda e: (e["week"], e["endpoint"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print one value per endpoint and ISO week from the AI Supply Index series, "
                    "using only usable rows (see 'Using the series' in README.md). Missing data is "
                    "printed as GAP, never as zero.")
    ap.add_argument("--series", default=str(DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", action="append", choices=sorted(VALUES), metavar="NAME",
                    help="only this endpoint; repeat for several (default: every endpoint in the series)")
    ap.add_argument("--json", action="store_true", help="print one JSON object per line instead of a table")
    a = ap.parse_args(argv)

    try:
        entries = weekly(read_rows(a.series), a.endpoint)
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1

    try:
        _print(entries, a.json)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 0


def _print(entries, as_json):
    for e in entries:
        if as_json:
            print(json.dumps(e, ensure_ascii=False))
        elif e["value"] is None:
            print("%s  %-28s  GAP (%s)" % (e["week"], e["endpoint"], e["gap"]))
        else:
            print("%s  %-28s  %-20s  %s  [%s]" % (e["week"], e["endpoint"], format(e["value"], ",.10g"),
                                                  e["zaman_utc"], VALUES[e["endpoint"]][0]))


if __name__ == "__main__":
    sys.exit(main())
