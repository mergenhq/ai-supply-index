#!/usr/bin/env python3
"""weekly_brief.py — a one-page Markdown brief of one ISO week of the AI Supply Index series.

For the chosen week (default: the last week in the series) it lists, per endpoint:
  - the weekly value, as examples/weekly_series.py gives it (reused by import, so the README
    selection rules apply unchanged), with the run it comes from;
  - the change against the previous week and against N weeks earlier (default 4): absolute, and
    in percent when the earlier value is not 0;
  - for endpoints whose chosen row carries distribution fields (objects with n and p50), the
    share of the total held by the largest value and by the ten largest (top1_pay, top10_pay).

Missing data is never shown as 0 and never compared: a week without a usable value reads
"no usable value (<reason>)", and a change against a gap week reads "n/a". Shares that the row
does not carry (the total was 0) read "n/a" as well.

Standard library only. Usage:
    python3 examples/weekly_brief.py > brief.md
    python3 examples/weekly_brief.py --week 2026-W38 --compare 2
    python3 examples/weekly_brief.py --json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)


def change(now, before):
    """{"from", "to", "abs", "pct"} or None when either side is missing; pct None when before is 0."""
    if now is None or before is None:
        return None
    d = now - before
    d = round(d, 4) if isinstance(d, float) else d
    return {"from": before, "to": now, "abs": d,
            "pct": None if before == 0 else round(100.0 * (now - before) / abs(before), 2)}


def _shares(ozet):
    out = []
    for field, d in sorted(ozet.items()):
        if isinstance(d, dict) and "n" in d and "p50" in d:
            out.append({"field": field, "n": d.get("n"), "top1_pay": d.get("top1_pay"),
                        "top10_pay": d.get("top10_pay")})
    return out


def brief(rows, week=None, compare=4):
    """Dict with week, weeks (all weeks in the series), compare, and one entry per endpoint."""
    entries = weekly_series.weekly(rows)
    if not entries:
        return {"week": week, "weeks": [], "compare": compare, "endpoints": []}
    all_weeks = weekly_series._weeks(min(e["week"] for e in entries), max(e["week"] for e in entries))
    week = week or all_weeks[-1]
    if week not in all_weeks:
        raise ValueError("week %s is not in the series (%s .. %s)" % (week, all_weeks[0], all_weeks[-1]))
    i = all_weeks.index(week)
    prev = all_weeks[i - 1] if i >= 1 else None
    back = all_weeks[i - compare] if compare and i >= compare else None
    by = {(e["week"], e["endpoint"]): e for e in entries}
    rows_by = {(r.get("zaman_utc"), r.get("uc")): r for r in rows}
    out = []
    for name in sorted({e["endpoint"] for e in entries}):
        e = by.get((week, name))
        if e is None:
            continue                                   # endpoint starts after this week
        value = e["value"]
        p = by.get((prev, name)) if prev else None
        b = by.get((back, name)) if back else None
        entry = {"endpoint": name, "what": weekly_series.VALUES[name][0], "value": value,
                 "zaman_utc": e.get("zaman_utc"), "gap": e.get("gap"),
                 "vs_previous": change(value, p["value"]) if p else None,
                 "vs_earlier": change(value, b["value"]) if b else None,
                 "shares": _shares(rows_by[(e["zaman_utc"], name)]["ozet"]) if value is not None else []}
        out.append(entry)
    return {"week": week, "weeks": [all_weeks[0], all_weeks[-1]], "previous": prev, "earlier": back,
            "compare": compare, "endpoints": out}


def _num(v):
    return "n/a" if v is None else format(v, ",.10g")


def _chg(c):
    if c is None:
        return "n/a"
    pct = "" if c["pct"] is None else " (%+.2f %%)" % c["pct"]
    return "%s%s" % (format(c["abs"], "+,.10g"), pct)


def _share(v):
    return "n/a" if v is None else "%.1f %%" % (100 * v)


def markdown(b, source):
    lines = ["# AI Supply Index — %s" % b["week"], ""]
    lines.append("Source: `%s` (sha256 %s…), weeks %s to %s. Weekly values follow the selection rules "
                 "in the README section \"Using the series\"; missing data is shown as missing, never "
                 "as 0." % (source["name"], source["sha256"][:16], b["weeks"][0], b["weeks"][1]))
    lines += ["", "## Values", ""]
    earlier = "vs %s" % b["earlier"] if b["earlier"] else "vs %d weeks earlier" % b["compare"]
    lines.append("| endpoint | value | what | vs %s | %s | run |" % (b["previous"] or "previous week", earlier))
    lines.append("|---|---:|---|---:|---:|---|")
    for e in b["endpoints"]:
        value = _num(e["value"]) if e["value"] is not None else "no usable value (%s)" % e["gap"]
        lines.append("| `%s` | %s | %s | %s | %s | %s |" % (
            e["endpoint"], value, e["what"], _chg(e["vs_previous"]), _chg(e["vs_earlier"]), e["zaman_utc"] or ""))
    shares = [(e["endpoint"], s) for e in b["endpoints"] for s in e["shares"]]
    if shares:
        lines += ["", "## Concentration", "",
                  "Share of each distribution's total held by its largest value and by its ten largest values.", "",
                  "| endpoint | field | n | largest | ten largest |", "|---|---|---:|---:|---:|"]
        for name, s in shares:
            lines.append("| `%s` | `%s` | %s | %s | %s |" % (name, s["field"], _num(s["n"]), _share(s["top1_pay"]),
                                                          _share(s["top10_pay"])))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Write a one-page Markdown brief of one ISO week of the AI Supply Index series: "
                    "each endpoint's weekly value (as examples/weekly_series.py gives it), its change "
                    "against the previous week and against N weeks earlier, and the top1/top10 shares "
                    "of its distributions. Missing data is shown as missing, never as 0.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--week", metavar="YYYY-Www", help="the ISO week to describe (default: the last week)")
    ap.add_argument("--compare", type=int, default=4, metavar="N",
                    help="also compare with N weeks earlier (default: 4; 0 to leave it out)")
    ap.add_argument("--json", action="store_true", help="print the brief as one JSON object instead of Markdown")
    a = ap.parse_args(argv)
    if a.compare < 0:
        ap.error("--compare must be 0 or more")

    try:
        data = Path(a.series).read_bytes()
        b = brief(weekly_series.read_rows(a.series), a.week, a.compare)
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    if not b["endpoints"]:
        print("error: the series has no rows the weekly tools can use", file=sys.stderr)
        return 1
    source = {"name": Path(a.series).name, "sha256": hashlib.sha256(data).hexdigest()}
    if a.json:
        print(json.dumps(dict(b, source=source), ensure_ascii=False, indent=1))
    else:
        sys.stdout.write(markdown(b, source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
