#!/usr/bin/env python3
"""report_html.py — the weekly values of the AI Supply Index as one standalone HTML page.

The page has one table per endpoint with the rows that examples/weekly_series.py prints (reused by
import, so the README selection rules apply unchanged): ISO week, value, the run it comes from,
and, for a week without a usable value, the reason. A gap leaves the value cell empty; it is never
written as 0. The page has no JavaScript and loads nothing: the styles are inline in the page.

Every table is <table id="endpoint-NAME"> with the columns week, value, run, gap; every value
cell carries data-value with the exact number (empty cells have no data-value).

Standard library only. Usage:
    python3 examples/report_html.py --out weekly.html
    python3 examples/report_html.py --endpoint x402_discovery --endpoint apify_store > two.html
"""
import argparse
import hashlib
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

STYLE = """
:root { --fg: #1d1d1f; --muted: #6b6b70; --bg: #ffffff; --line: #e2e2e6; --gap: #f6f6f8; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #ececf0; --muted: #a0a0a8; --bg: #16161a; --line: #34343a; --gap: #202026; }
}
body { font-family: system-ui, sans-serif; color: var(--fg); background: var(--bg);
       max-width: 860px; margin: 2rem auto; padding: 0 16px; line-height: 1.45; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
p.meta, p.what { color: var(--muted); font-size: 0.9rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--line); }
td.value { text-align: right; font-variant-numeric: tabular-nums; }
tr.gap td { background: var(--gap); color: var(--muted); }
"""


def _fmt(v):
    return format(v, ",.10g")


def page(entries, source_name, source_sha):
    """The HTML text for weekly_series.weekly() entries."""
    by = {}
    for e in entries:
        by.setdefault(e["endpoint"], []).append(e)
    weeks = sorted({e["week"] for e in entries})
    span = "%s to %s" % (weeks[0], weeks[-1]) if weeks else "no weeks"
    out = ["<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           "<title>AI Supply Index weekly values</title>", "<style>%s</style>" % STYLE, "</head>", "<body>",
           "<h1>AI Supply Index — weekly values</h1>",
           '<p class="meta">Source: %s (sha256 %s…), ISO weeks %s. One value per endpoint and week, from the '
           "last usable row of the week (README, \"Using the series\"). An empty value is missing data, "
           "not 0.</p>" % (escape(source_name), escape(source_sha[:16]), escape(span))]
    for name in sorted(by):
        out.append('<h2 id="h-%s">%s</h2>' % (escape(name), escape(name)))
        out.append('<p class="what">%s</p>' % escape(weekly_series.VALUES[name][0]))
        out.append('<table id="endpoint-%s">' % escape(name))
        out.append("<thead><tr><th>week</th><th>value</th><th>run</th><th>gap</th></tr></thead><tbody>")
        for e in sorted(by[name], key=lambda x: x["week"]):
            if e["value"] is None:
                out.append('<tr class="gap"><td>%s</td><td class="value"></td><td></td><td>%s</td></tr>'
                           % (escape(e["week"]), escape(e["gap"])))
            else:
                out.append('<tr><td>%s</td><td class="value" data-value="%s">%s</td><td>%s</td><td></td></tr>'
                           % (escape(e["week"]), escape(repr(e["value"])), escape(_fmt(e["value"])),
                              escape(e["zaman_utc"])))
        out.append("</tbody></table>")
    if not by:
        out.append("<p>No endpoint has rows in this series.</p>")
    out += ["</body>", "</html>"]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Write one standalone HTML page with a table per endpoint of the weekly values "
                    "examples/weekly_series.py prints (week, value, run, gap). Gaps are empty, never 0. "
                    "No JavaScript and no external files.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", action="append", choices=sorted(weekly_series.VALUES), metavar="NAME",
                    help="only this endpoint; repeat for several (default: every endpoint in the series)")
    ap.add_argument("--out", default="-", help="file to write the page to (default: standard output)")
    a = ap.parse_args(argv)

    try:
        data = Path(a.series).read_bytes()
        html = page(weekly_series.weekly(weekly_series.read_rows(a.series), a.endpoint),
                    Path(a.series).name, hashlib.sha256(data).hexdigest())
        if a.out == "-":
            sys.stdout.write(html)
        else:
            Path(a.out).write_text(html, encoding="utf-8")
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
