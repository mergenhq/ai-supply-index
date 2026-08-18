#!/usr/bin/env bash
# kos_haftalik.sh — AI-arz toplayicisinin HAFTALIK kosu sarmalayicisi (s189 T1-icra 2026-08-18)
#
# UC ADIM, her biri ayri rc ile loglanir:
#   1) TOPLA    — ai_arz_toplayici.py (10 uc, kimliksiz public GET)
#   2) MUHURLE  — DEVIR §3.1 kurali: "Her OTS muhru, iceriginin DEGISMEZ kopyasiyla saklanacak"
#                 => hareketli seriyi degil, tarihli DONMUS anlik-kopyayi damgalar
#   3) DENETLE  — tazelik bekcisi (tuketici; kural-16c)
#
# NEDEN VPS: Mac uyursa kacan hafta GERI ALINAMAZ (x402 rolling-30g, apify kayan-pencere,
# sherlock kumulatif => tarihsel uc yok). BENIOKU.md aciliyet gerekcesi.
set -uo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERI="$KOK/ai-arz-serisi.ndjson"
ARSIV="$KOK/arsiv"
DAMGA="$(date -u +%Y%m%dT%H%M%SZ)"
say() { echo "$(date -u +%FT%TZ) $*"; }

say "=== ADIM-1 TOPLA ==="
cd "$KOK" || exit 1
python3 ai_arz_toplayici.py
RC_TOPLA=$?
say "ADIM-1 rc=$RC_TOPLA"

say "=== ADIM-2 MUHURLE (donmus anlik-kopya) ==="
if [ "$RC_TOPLA" -eq 0 ] && [ -s "$SERI" ]; then
  mkdir -p "$ARSIV"
  KOPYA="$ARSIV/ai-arz-serisi-$DAMGA.ndjson"
  cp "$SERI" "$KOPYA"
  say "donmus kopya: $(basename "$KOPYA") ($(wc -l < "$KOPYA") satir)"
  # ots console-script cron-PATH'inde OLMAYABILIR => ayni-interpreter deseni (insight_writer.py emsali)
  python3 -c "import sys; sys.argv=['ots','stamp',sys.argv[1]]; from otsclient.ots import main; main()" "$KOPYA"
  say "ADIM-2 rc=$? muhur=$(basename "$KOPYA").ots"
else
  say "ADIM-2 ATLANDI (toplama basarisiz veya seri bos) — muhur YOK"
fi

say "=== ADIM-3 DENETLE (tazelik bekcisi) ==="
python3 "$KOK/ai_arz_tazelik_bekci.py" --defter "$HOME/logs/ai-arz-alarm.ndjson"
RC_BEKCI=$?
say "ADIM-3 rc=$RC_BEKCI (0=YESIL 1=SARI 2=KIRMIZI)"

say "=== BITTI topla=$RC_TOPLA bekci=$RC_BEKCI ==="
exit "$RC_TOPLA"
