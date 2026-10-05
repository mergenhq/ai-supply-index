#!/usr/bin/env python3
"""leaders.py — who is in the published top lists, week by week, and how the ranks move.

Five endpoints archive a ranked list next to their totals:

  x402_discovery            top10_cagri   resource (kaynak)          30-day paid calls (cagri)
  sherlock_leaderboard      top10         handle                     lifetime payout, USD (odeme)
  apify_store               top10         actor (aktor)              total users (kullanici)
  hf_models                 top10         model id                   downloads, moving window (indirme)
  defillama_fees_ai_agents  ai_top5_30d   protocol name (ad)         30-day fees, USD (usd30d)

For every ISO week the list comes from the row that examples/weekly_series.py picks (reused by
import, so the README selection rules apply unchanged). The rank is the position in the published
list (1 = first). Each entry is compared with the previous week:

  same / up / down   on the list both weeks (moved = places gained, negative when it fell)
  new                not on the previous week's list
  left               on the previous week's list, not on this one (rank and value are empty)
  no comparison      the previous week is a gap, or this is the first week

A week without a usable row is a gap; nothing is invented for it, and the week after it is
compared with nothing rather than with an empty list.

Standard library only. Usage:
    python3 examples/leaders.py --endpoint defillama_fees_ai_agents
    python3 examples/leaders.py --endpoint x402_discovery --changes-only --csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

# endpoint -> (list key in ozet, name key, value key, what the value is)
LISTS = {
    "x402_discovery": ("top10_cagri", "kaynak", "cagri", "30-day paid calls"),
    "sherlock_leaderboard": ("top10", "handle", "odeme", "lifetime payout (USD)"),
    "apify_store": ("top10", "aktor", "kullanici", "total users"),
    "hf_models": ("top10", "id", "indirme", "downloads (moving window)"),
    "defillama_fees_ai_agents": ("ai_top5_30d", "ad", "usd30d", "30-day fees (USD)"),
}
COLUMNS = ["week", "endpoint", "rank", "name", "value", "status", "moved", "zaman_utc", "gap"]


def ranked(ozet, endpoint):
    """[(rank, name, value)] from one summary, in published order; None when the list is absent."""
    key, name_key, value_key, _ = LISTS[endpoint]
    items = ozet.get(key) if isinstance(ozet, dict) else None
    if not isinstance(items, list):
        return None
    out = []
    for i, it in enumerate(items, 1):
        if isinstance(it, dict) and it.get(name_key) is not None:
            v = it.get(value_key)
            out.append((i, str(it[name_key]), v if isinstance(v, (int, float)) and not isinstance(v, bool) else None))
    return out


def leaders(rows, endpoint, changes_only=False):
    """Entries (dicts with COLUMNS) per week, in week order; within a week by rank, then 'left'."""
    by_key = {(r.get("zaman_utc"), r.get("uc")): r for r in rows}
    out, previous = [], None
    for e in weekly_series.weekly(rows, [endpoint]):
        base = {"week": e["week"], "endpoint": endpoint}
        lst = (ranked(by_key[(e["zaman_utc"], endpoint)]["ozet"], endpoint)
               if e["value"] is not None else None)
        if lst is None:
            reason = e.get("gap") or "list not in this row"
            if not changes_only:
                out.append(dict(base, rank=None, name=None, value=None, status=None, moved=None,
                                zaman_utc=e.get("zaman_utc") if e["value"] is not None else None, gap=reason))
            previous = None
            continue
        before = {name: rank for rank, name, _ in previous} if previous is not None else None
        week_rows = []
        for rank, name, value in lst:
            if before is None:
                status, moved = "no comparison", None
            elif name not in before:
                status, moved = "new", None
            else:
                moved = before[name] - rank
                status = "same" if moved == 0 else ("up" if moved > 0 else "down")
            week_rows.append(dict(base, rank=rank, name=name, value=value, status=status, moved=moved,
                                  zaman_utc=e["zaman_utc"]))
        if before is not None:
            now = {name for _, name, _ in lst}
            for rank, name, _ in previous:
                if name not in now:
                    week_rows.append(dict(base, rank=None, name=name, value=None, status="left",
                                          moved=None, zaman_utc=e["zaman_utc"]))
        if changes_only:
            week_rows = [r for r in week_rows if r["status"] in ("new", "left", "up", "down")]
        out.extend(week_rows)
        previous = lst
    return out


def write_csv(entries, out):
    """CSV with COLUMNS; a missing value is an empty cell, never 0."""
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for e in entries:
        w.writerow(["" if e.get(c) is None else (repr(e[c]) if c == "value" else e[c]) for c in COLUMNS])


def _text(entries, endpoint):
    print("%s: rank, name, %s, change against the previous week" % (endpoint, LISTS[endpoint][3]))
    for e in entries:
        if e.get("gap"):
            print("%s  GAP (%s)" % (e["week"], e["gap"]))
            continue
        rank = "-" if e["rank"] is None else str(e["rank"])
        value = "" if e["value"] is None else format(e["value"], ",.10g")
        change = e["status"] + ("" if e["moved"] in (None, 0) else " %+d" % e["moved"])
        name = e["name"] if len(e["name"]) <= 60 else e["name"][:57] + "..."
        print("%s  %3s  %-60s  %16s  %s" % (e["week"], rank, name, value, change))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print the published top list of one endpoint per ISO week (x402_discovery, "
                    "sherlock_leaderboard, apify_store, hf_models, defillama_fees_ai_agents) with each "
                    "entry's rank change against the previous week: same, up, down, new or left. Rows "
                    "are selected as in examples/weekly_series.py; a gap week is printed as GAP and "
                    "the week after it is not compared.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", required=True, choices=sorted(LISTS), help="the endpoint whose list to print")
    ap.add_argument("--changes-only", dest="changes_only", action="store_true",
                    help="print only entries that are new, left, or moved up or down")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print one JSON object per line")
    fmt.add_argument("--csv", action="store_true",
                     help="print CSV with the columns %s; missing values are empty" % ",".join(COLUMNS))
    a = ap.parse_args(argv)

    try:
        entries = leaders(weekly_series.read_rows(a.series), a.endpoint, a.changes_only)
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
            _text(entries, a.endpoint)
    except BrokenPipeError:          # e.g. piped into `head`
        sys.stderr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
