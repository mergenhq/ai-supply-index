#!/usr/bin/env python3
"""svg_chart.py — the weekly value of one endpoint as a standalone SVG line chart.

The values are exactly what examples/weekly_series.py prints for the endpoint (reused by import):
one value per ISO week from the last usable row of the week. A week without a usable value breaks
the line: it is never drawn as 0. Gap weeks are marked under the x axis so they stay visible.

The chart has a title, a labelled x axis (ISO week) and a labelled y axis (what the value is,
from weekly_series.VALUES) with tick values. Every point is a <circle> carrying data-week and
data-value attributes; every unbroken run of weeks is one <polyline>.

Standard library only. Usage:
    python3 examples/svg_chart.py --endpoint x402_discovery --out x402.svg
    python3 examples/svg_chart.py --endpoint apify_store > apify.svg
"""
import argparse
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_series  # noqa: E402  (same directory)

WIDTH, HEIGHT = 820, 420
LEFT, RIGHT, TOP, BOTTOM = 110, 30, 50, 80
LINE, MUTED, GRID = "#1f6fb2", "#8a8a8a", "#e3e3e3"


def nice_ticks(lo, hi, count=5):
    """Round tick values covering [lo, hi]."""
    if lo == hi:
        lo, hi = (0, 1) if lo == 0 else (lo - abs(lo) * 0.1, hi + abs(hi) * 0.1)
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    if lo >= 0 > start:                    # non-negative data never gets a negative axis
        start = 0
    ticks, t = [], start
    while t <= hi + step * 1e-9:
        ticks.append(round(t, 10))
        t += step
    if ticks[-1] < hi:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def segments(points):
    """Split [(index, week, value|None)] into runs of consecutive weeks that all have a value."""
    runs, cur = [], []
    for p in points:
        if p[2] is None:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(p)
    if cur:
        runs.append(cur)
    return runs


def _fmt(v):
    return format(v, ",.6g")


def render(endpoint, entries):
    """SVG text for one endpoint's weekly_series.weekly() entries."""
    entries = sorted((e for e in entries if e["endpoint"] == endpoint), key=lambda e: e["week"])
    what = weekly_series.VALUES[endpoint][0]
    title = "%s: %s per ISO week" % (endpoint, what)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="sans-serif" font-size="12">' % (WIDTH, HEIGHT, WIDTH, HEIGHT),
           "<title>%s</title>" % escape(title),
           '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (WIDTH, HEIGHT),
           '<text class="chart-title" x="%d" y="28" font-size="15" font-weight="bold">%s</text>'
           % (LEFT, escape(title))]
    plot_w, plot_h = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    values = [e["value"] for e in entries if e["value"] is not None]
    if not values:
        out.append('<text class="no-data" x="%d" y="%d">no usable value in the series</text>'
                   % (LEFT, TOP + plot_h // 2))
        out.append("</svg>")
        return "\n".join(out) + "\n"

    ticks = nice_ticks(min(values), max(values))
    lo, hi = ticks[0], ticks[-1]
    n = len(entries)

    pad = 14                                 # keep end points off the axes

    def x(i):
        return LEFT + pad + ((plot_w - 2 * pad) / 2 if n == 1 else (plot_w - 2 * pad) * i / (n - 1))

    def y(v):
        return TOP + plot_h - plot_h * (v - lo) / (hi - lo)

    # y axis: grid, ticks, label
    out.append('<g class="y-axis">')
    for t in ticks:
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>' % (LEFT, y(t), WIDTH - RIGHT, y(t), GRID))
        out.append('<text class="tick" x="%d" y="%.1f" text-anchor="end" dominant-baseline="middle">%s</text>'
                   % (LEFT - 8, y(t), escape(_fmt(t))))
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (LEFT, TOP, LEFT, TOP + plot_h))
    out.append('<text class="axis-label" x="20" y="%d" transform="rotate(-90 20 %d)" text-anchor="middle">%s</text>'
               % (TOP + plot_h // 2, TOP + plot_h // 2, escape(what)))
    out.append("</g>")

    # x axis: one tick per week, labels thinned to at most 12, gap weeks marked
    every = max(1, math.ceil(n / 12))
    out.append('<g class="x-axis">')
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (LEFT, TOP + plot_h, WIDTH - RIGHT, TOP + plot_h))
    for i, e in enumerate(entries):
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#333"/>' % (x(i), TOP + plot_h, x(i), TOP + plot_h + 4))
        if i % every == 0 or i == n - 1:
            out.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%s</text>'
                       % (x(i), TOP + plot_h + 18, escape(e["week"])))
    out.append('<text class="axis-label" x="%d" y="%d" text-anchor="middle">ISO week</text>'
               % (LEFT + plot_w // 2, HEIGHT - 18))
    out.append("</g>")

    gaps = [(i, e) for i, e in enumerate(entries) if e["value"] is None]
    if gaps:
        out.append('<g class="gaps">')
        for i, e in gaps:
            out.append('<text class="gap" data-week=%s x="%.1f" y="%d" text-anchor="middle" fill="%s">gap'
                       '<title>%s: no usable value (%s)</title></text>'
                       % (quoteattr(e["week"]), x(i), TOP + plot_h + 34, MUTED, escape(e["week"]), escape(e["gap"])))
        out.append("</g>")

    # the line: one polyline per unbroken run, one circle per point
    points = [(i, e["week"], e["value"]) for i, e in enumerate(entries)]
    out.append('<g class="series">')
    for run in segments(points):
        if len(run) > 1:
            out.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>'
                       % (LINE, " ".join("%.1f,%.1f" % (x(i), y(v)) for i, _, v in run)))
    for i, week, v in points:
        if v is not None:
            out.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="%s" data-week=%s data-value=%s>'
                       '<title>%s: %s</title></circle>'
                       % (x(i), y(v), LINE, quoteattr(week), quoteattr(repr(v)), escape(week), escape(_fmt(v))))
    out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Draw the weekly value of one endpoint of the AI Supply Index series (as "
                    "examples/weekly_series.py prints it) as a standalone SVG line chart. A week "
                    "without a usable value breaks the line and is never drawn as 0.")
    ap.add_argument("--series", default=str(weekly_series.DEFAULT_SERIES),
                    help="path to the NDJSON series (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--endpoint", required=True, choices=sorted(weekly_series.VALUES), metavar="NAME",
                    help="the endpoint to draw (one of: %s)" % ", ".join(sorted(weekly_series.VALUES)))
    ap.add_argument("--out", default="-", help="file to write the SVG to (default: standard output)")
    a = ap.parse_args(argv)

    try:
        svg = render(a.endpoint, weekly_series.weekly(weekly_series.read_rows(a.series), [a.endpoint]))
        if a.out == "-":
            sys.stdout.write(svg)
        else:
            Path(a.out).write_text(svg, encoding="utf-8")
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
