#!/usr/bin/env bash
# run_weekly.sh — WEEKLY run wrapper for the AI Supply Index collector.
#
# THREE STEPS, each logged with its own return code:
#   1) COLLECT — collector.py (11 endpoints, unauthenticated public GETs)
#   2) STAMP   — rule: "every OpenTimestamps seal is kept next to an IMMUTABLE copy of what
#                it sealed" => we stamp a dated FROZEN snapshot, never the moving series.
#   3) AUDIT   — freshness_watchdog.py (the consumer; an independent daily run is what stops
#                a dead watchdog from looking like a healthy one)
#
# WHY ON A SERVER AND NOT A LAPTOP: if the laptop is asleep the missed week CANNOT BE
# RECOVERED (x402 is a rolling 30 days, Apify is a sliding window, Sherlock is cumulative
# with no historical endpoint). See README.md for the full reasoning.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERIES="$ROOT/ai-arz-serisi.ndjson"
ARCHIVE="$ROOT/archive"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
say() { echo "$(date -u +%FT%TZ) $*"; }

say "=== STEP-1 COLLECT ==="
cd "$ROOT" || exit 1
python3 collector.py
RC_COLLECT=$?
say "STEP-1 rc=$RC_COLLECT"

say "=== STEP-2 STAMP (frozen snapshot) ==="
if [ "$RC_COLLECT" -eq 0 ] && [ -s "$SERIES" ]; then
  mkdir -p "$ARCHIVE"
  COPY="$ARCHIVE/ai-arz-serisi-$STAMP.ndjson"
  cp "$SERIES" "$COPY"
  say "frozen copy: $(basename "$COPY") ($(wc -l < "$COPY") lines)"
  # the `ots` console script may not be on cron's PATH => call it through the same interpreter
  python3 -c "import sys; sys.argv=['ots','stamp',sys.argv[1]]; from otsclient.ots import main; main()" "$COPY"
  say "STEP-2 rc=$? seal=$(basename "$COPY").ots"
else
  say "STEP-2 SKIPPED (collection failed or series empty) — NO seal written"
fi

say "=== STEP-3 AUDIT (freshness watchdog) ==="
python3 "$ROOT/freshness_watchdog.py" --ledger "$HOME/logs/ai-arz-alarm.ndjson"
RC_WATCHDOG=$?
say "STEP-3 rc=$RC_WATCHDOG (0=GREEN 1=YELLOW 2=RED)"

say "=== DONE collect=$RC_COLLECT watchdog=$RC_WATCHDOG ==="
exit "$RC_COLLECT"
