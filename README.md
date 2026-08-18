# AI Supply Index — who is actually earning in the AI economy?

**A weekly, timestamped, independently collected record of the *supply side* of the AI economy.**

Most public measurement covers **demand** — how many people use AI, for what. The supply side
(who is actually earning, and how concentrated those earnings are) is measured far less often,
and several of the sources that would answer it **do not keep history**. A snapshot not taken
this week cannot be reconstructed later.

This repository is that snapshot, taken every Monday, with the method open and the raw series public.

---

## First measurement — 2026-08-18

| endpoint | what it measures | value |
|---|---|---|
| DefiLlama (AI-Agents category) | protocol fee revenue, 30d | **$1,177,308** across **17** protocols |
| → concentration | share of the single largest | **89.7 %** (Virtuals Protocol, $1,055,670) |
| Sherlock (security-audit contests) | researchers with lifetime payouts | **1,710** researchers · **$15,762,894** lifetime |
| Sherlock contests | contests listed | **301** (open right now: **0**) |
| x402 (agent payment discovery) | resources registered | **15,149** · 30d calls **322,375** |
| Apify store | published actors | **47,257** (top 1,000 by popularity sampled) |
| Hugging Face | downloads, top 100 AI-agent models | **1.58 B** |
| npm / PyPI | SDK download volume | Anthropic SDK: **115.9 M** (npm, 30d) |
| GitHub | agent-framework repos | AutoGPT 186,664 ★ · langchain 144,478 ★ · MCP servers 89,659 ★ |

### What stands out in week 1

**Concentration.** In the AI-agent protocol category, **89.7 % of 30-day fee revenue sits in one
protocol**. The remaining 16 protocols share roughly $121,600 between them. Whatever "the agent
economy" is earning, it is not earning it broadly — at least not yet, and not here.

**A closed door.** Of 301 audit contests listed on Sherlock, **zero are open right now**
(verified across all 31 result pages, 2026-08-18). Payout infrastructure exists — $15.8 M has been
distributed — but access to it is intermittent, not continuous. Anyone modelling "just go earn on
audit platforms" should measure the *cadence of open windows*, not the existence of the platform.

---

## Method

- **10 endpoints**, all public, **no authentication, no account, no scraping of gated content**
- One run ≈ 73 seconds, cost **$0**
- Every run appends one line per endpoint to `ai-arz-serisi.ndjson` (JSON Lines, append-only)
- Runs weekly (Mondays, 07:00 UTC) plus an **independent daily freshness watchdog** — because a
  collector that silently returns zero is worse than one that visibly fails
- Each record carries `zaman_utc`, `uc` (endpoint), `ozet` (summary), `durum` (status), `saniye` (duration)
- Series is **OpenTimestamps-anchored** so that "we measured this on that date" is verifiable, not asserted

### Known limits (stated, not hidden)

1. **Summaries only.** Raw API payloads are not stored (size); a `bayt` field records payload size for control.
2. **Sampling where the source paginates.** Apify: top 1,000 of 47,257 by popularity. Hugging Face: top 100.
   These are **upper-tier samples, not medians** — treat them as such.
3. **Schema fragility.** If an endpoint changes shape, a naive reader returns 0 silently. This happened to us
   on day one (`contests` vs `items`), which is why the freshness watchdog checks for silent zeros, frozen
   counters and missing endpoints — not just staleness.
4. **Ten endpoints is not the supply side.** It is ten measurable corners of it. Coverage will be stated
   with every expansion.
5. **Short history.** As of this publication the series is **days old**. Its value compounds; it does not
   start high.

---

## Conflict of interest

The author operates automated trading systems on prediction markets (Kalshi, Hyperliquid, Polymarket),
and is therefore **not a neutral party** with respect to the economics of AI-driven trading.
Two of the tracked endpoints (Sherlock, x402) are markets the author could plausibly participate in.

The defence offered here is not neutrality but **method transparency**: every number is reproducible from
the published collector and the raw series, and every limit above is stated before anyone asks.

Additionally: this measurement is produced with substantial AI assistance. An AI-assisted system measuring
the AI economy is itself a conflict worth naming.

---

## Reproduce it

```bash
python3 ai_arz_toplayici.py      # one run, ~73 s, no credentials
```

Raw series: `ai-arz-serisi.ndjson` · Collector: `ai_arz_toplayici.py` · Watchdog: `ai_arz_tazelik_bekci.py`

---

*Corrections welcome. If a number here is wrong, open an issue with the endpoint and the counter-measurement;
it will be fixed in the next weekly run and the correction recorded in the series.*
