# AI Supply Index — who is actually earning in the AI economy?

**A weekly, timestamped, independently collected record of the *supply side* of the AI economy.**

Most public measurement covers **demand** — how many people use AI, for what. The supply side
(who is actually earning, and how concentrated those earnings are) is measured far less often,
and several of the sources that would answer it **do not keep history**. A snapshot not taken
this week cannot be reconstructed later.

This repository is that snapshot, taken twice a week, with the method open and the raw series public.

---

## First measurement — 2026-08-18

| endpoint | what it measures | value | run (`zaman_utc`) |
|---|---|---|---|
| DefiLlama (AI-Agents category) | protocol fees, 30d | **$1,177,308** across **17** protocols | `2026-08-18T07:51:45Z` |
| → concentration | share of the single largest | **89.7 %** (Virtuals Protocol, $1,055,670) | `2026-08-18T07:51:45Z` |
| Sherlock (security-audit contests) | researchers listed, lifetime payouts | **1,710** researchers listed (1,698 with a payout above 0) · **$15,762,894** lifetime | `2026-08-18T07:51:45Z` |
| Sherlock contests | contests listed | **301** (open right now: **0**) | `2026-08-18T16:27:27Z` (first run that counted open contests) |
| x402 (agent payment discovery) | resources registered | **15,149** · 30d calls **322,375** | `2026-08-18T15:04:11Z` |
| Apify store | published actors | **47,257** (top 1,000 by popularity sampled) | `2026-08-18T15:04:11Z` |
| Hugging Face | downloads, top 100 models on the Hub (all kinds, by downloads) | **1.58 B** | `2026-08-18T15:04:11Z` |
| npm / PyPI | SDK download volume | Anthropic SDK: **115.9 M** (npm, 30d) | `2026-08-18T07:51:45Z` |
| GitHub | agent-framework repos | AutoGPT 186,664 ★ · langchain 144,478 ★ · MCP servers 89,659 ★ | `2026-08-18T15:04:11Z` |

Every number above is recomputable from `ai-arz-serisi.ndjson` in this repository: select the rows whose
`zaman_utc` is the run named in the last column. The table is the 2026-08-18 baseline and is not updated;
later values are in the series.

### What stands out in week 1

**Concentration.** In the AI-agent protocol category, **89.7 % of 30-day fees sits in one
protocol**. The remaining 16 protocols share roughly $121,600 between them. Whatever "the agent
economy" is earning, it is not earning it broadly — at least not yet, and not here.

**A closed door.** Of 301 audit contests listed on Sherlock, **zero are open right now**
(verified across every result page, 2026-08-18). Payout infrastructure exists — $15.8 M has been
distributed — but access to it is intermittent, not continuous. Anyone modelling "just go earn on
audit platforms" should measure the *cadence of open windows*, not the existence of the platform.

That finding is why an eleventh endpoint (Code4rena) was added right after this first measurement:
one platform being shut is an anecdote, two is the beginning of a pattern. Its rows enter the
series from the `2026-08-18T16:31:07Z` run onward — this table deliberately reports only rows from
earlier runs.

---

## Method

- **11 endpoints**, all public, **no authentication, no account, no scraping of gated content**
- A complete run takes about **70–190 seconds** for all 11 endpoints (median ≈ 100 s up to 2026-09-28; `saniye` per row);
  runs with failed endpoints took up to about an hour (2,317–3,692 s). Cost **$0**
- Every run appends one line per endpoint to `ai-arz-serisi.ndjson` (JSON Lines, append-only)
- Runs **twice a week, Mondays and Thursdays 07:00 UTC**, plus an **independent daily freshness watchdog
  at 07:30 UTC** — because a collector that silently returns zero is worse than one that visibly fails.
  The series also holds the set-up runs of 2026-08-18 to 2026-08-21 (up to six a day), and from 2026-08-20
  to 2026-09-14 a second collector ran at about 06:30 UTC, so most of those days carry two runs. Rows written by a
  collector that sets `AI_ARZ_TOPLAYICI` carry its name in `toplayici` (`collector_id`).
- Record structure is documented key by key in [**Schema**](#schema) below
- Each publication is **OpenTimestamps-stamped**: the series is copied to a frozen, dated snapshot under
  [`archive/`](archive/) and that snapshot is stamped next to it (`archive/ai-arz-serisi-<UTC stamp>.ndjson.ots`),
  so that "we measured this on that date" is verifiable, not asserted. The newest snapshot is byte-identical
  to `ai-arz-serisi.ndjson` at the time of publication. Each stamp covers its own snapshot only — the series
  is append-only, so earlier stamps do not validate later files.
  **Status:** a stamp is first submitted to calendar servers; Bitcoin anchoring takes hours, so `ots verify`
  reads *pending* until a block confirms it.
- `ai-arz-serisi.ndjson.ots` at the repository root is the stamp of the 2026-08-24 version of the series
  (133 rows, sha256 `a1a625642dad9d91…`, commit `baee016`). It is kept as published; it does not cover the
  current file. Use the newest proof under `archive/` instead.
- A dated, append-only [**evidence record**](record/) of what this system measured about itself — negatives mandatory, entries never edited

### The silent-zero brake

If an upstream response changes shape, the naive outcome is that a counter quietly becomes `0` and
nobody notices — the file still grows, the exit code is still `0`, and the series records a
confident lie. That happened to this project on day one (`contests` vs `items`).

So the collector refuses to count zero when it cannot measure. It emits `olculemedi`
(`unmeasurable`) with a reason string instead, and the watchdog turns that red. **When you see
`unmeasurable` in a row, the accompanying value is not zero — it is unknown.** The distinction
matters for anyone using this series as evidence.

---

## Schema

The series keys are Turkish and **frozen** — see *Why the keys stay Turkish* below.
This table is the contract. It is generated from [`schema_map.json`](schema_map.json)
via `python3 to_english.py --schema-md`, so the two cannot drift apart.

#### Record envelope

*Present on every line of the series. One line = one endpoint in one run.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `zaman_utc` | `timestamp_utc` | string (ISO-8601, UTC) | when the run started; all rows of one run share this value, so it doubles as the run id |
| `surum` | `version` | string | collector version that wrote the row (absent on the very first v0.1 rows) |
| `uc` | `endpoint` | string | endpoint name, e.g. x402_discovery, github_repos |
| `not` | `note` | string | free-text annotation about the endpoint's limits; rows up to and including the 2026-08-18T16:31:07Z run carry Turkish text |
| `ozet` | `summary` | object | the measurement itself; its shape depends on the endpoint |
| `durum` | `status` | string | OK \| HATA (error) \| HTTP-HATA (http error) \| HATA-ICERIDE (error inside the summary) |
| `saniye` | `duration_s` | number (seconds) | wall-clock time this endpoint took |
| `http` | `http_status` | integer | HTTP status code; present when the request failed, and on the v0.1 rows, where it is 200 |
| `hata` | `error` | string | Python exception repr, truncated; only present on failure |
| `url` | `url` | string | on the envelope: the endpoint URL (v0.1 rows only); inside open entries (open_entries): the entry's page on the platform |
| `bayt` | `bytes` | integer | raw response size (v0.1 rows only); raw payloads are not stored |
| `toplayici` | `collector_id` | string | which collector host wrote the row (the AI_ARZ_TOPLAYICI setting, at most 40 characters); absent when not set |

#### Distribution summary

*Emitted by the shared `dagilim_ozeti` helper and reused wherever a distribution is archived (x402, Sherlock, Apify, Hugging Face, DeFiLlama). The distribution is the point: totals alone hide concentration.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `n` | `n` | integer | how many numeric values entered the distribution |
| `toplam` | `total` | number | sum of all values |
| `sifir_sayisi` | `zero_count` | integer | how many of the values were exactly 0 |
| `p10` | `p10` | number | 10th percentile, nearest-rank (the value at rank ceil(p/100 * n)), no interpolation. Rows with version up to 0.3 used index round((n-1) * p/100), which can differ by one rank for small n |
| `p25` | `p25` | number | 25th percentile |
| `p50` | `p50` | number | median |
| `p75` | `p75` | number | 75th percentile |
| `p90` | `p90` | number | 90th percentile |
| `p95` | `p95` | number | 95th percentile |
| `p99` | `p99` | number | 99th percentile |
| `maks` | `max` | number | largest single value |
| `histogram` | `histogram` | object | bucket label -> count; bucket labels are data (see passthrough) |
| `top1_pay` | `top1_share` | number (0-1) | share of the total held by the single largest value — the concentration measure |
| `top10_pay` | `top10_share` | number (0-1) | share of the total held by the ten largest values; it is 1.0 by construction whenever there are ten or fewer non-zero values (n minus zero_count) |

#### Pagination and coverage

*Shared across the paginated endpoints. These exist so a reader can tell a real zero from an unmeasured one.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `sayfa` | `pages_walked` | integer | how many pages the collector actually fetched |
| `sayfa_ogesi` | `page_items` | integer | how many items were collected across those pages |
| `sayfa_alani` | `pages_reported` | integer | page count the API itself reported (Sherlock) |
| `son_sayfa_alani` | `last_page_reported` | integer | last-page number the API reported (Code4rena) |
| `taranan` | `scanned` | integer | how many items yielded a usable numeric value |
| `kapsam_notu` | `coverage_note` | string | explicit statement of what this sample is and is not (e.g. upper tier, not a median) |
| `olculemedi` | `unmeasurable` | string (reason) | PRESENT ONLY WHEN THE MEASUREMENT IS INCOMPLETE: the schema broke, a page cap was reached, or values were missing (also inside a per-package sub-summary). If this key exists, the accompanying value is NOT zero — it is UNKNOWN. The collector refuses to silently count 0 when a response changes shape; it records why instead. Treat a row carrying `unmeasurable` as missing data, never as a measured zero. |

#### Open-window watch

*Endpoints sherlock_contests, code4rena_audits (and cantina_competitions, implemented but not yet wired). Answers 'how many doors are open right now', which is a different question from 'how many exist'.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `yarisma_sayisi` | `competition_count` | integer \| null | total competitions/audits the platform lists; null when unmeasurable |
| `acik_yarisma` | `open_count` | integer \| null | how many are open right now (end time in the future); null when unmeasurable |
| `acik_kamu` | `open_public_count` | integer \| null | of those, how many are open to the public (not private/invite-only) |
| `en_yeni_baslangic_utc` | `newest_start_utc` | string (ISO-8601, UTC) \| null | start time of the newest entry the platform lists; if even this is months old, the listing itself may have stopped updating and the open count describes the listing, not the platform |
| `acik_kapilar` | `open_entries` | array | the open ones themselves, soonest deadline first, capped at 10 per row to bound record size; the counts above are always exact |
| `arena` | `arena` | string | which platform the entry came from: sherlock \| code4rena \| cantina |
| `id` | `id` | string \| integer | platform's own identifier for the entry |
| `baslik` | `title` | string | entry title, truncated to 120 characters |
| `kamu` | `is_public` | boolean | true when the entry is open to anyone rather than invite-only |
| `biter_utc` | `ends_utc` | string (ISO-8601, UTC) | when the entry closes |
| `kalan_gun` | `days_left` | number (days) | days remaining at the moment of measurement |
| `odul` | `prize` | string \| number \| null | prize pool as the platform reports it (format varies by platform) |
| `etiket` | `label` | string | platform's own category label, e.g. contest type or audit type |
| `kyc` | `kyc_required` | boolean \| null | whether the platform requires identity verification (Cantina only) |

#### x402 discovery

*Agent-payment resource registry. ROLLING 30-DAY WINDOW: the upstream keeps no history, so a week not captured is gone.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `kaynak_sayisi` | `resource_count` | integer | resources registered in the discovery index |
| `cagri_30g` | `calls_30d` | object (distribution) | distribution of paid calls per resource over the last 30 days |
| `odeyen_30g` | `unique_payers_30d` | object (distribution) | distribution of unique payers per resource over the last 30 days |
| `top10_cagri` | `top10_by_calls` | array | the ten most-called resources |
| `cagri` | `calls` | integer | call count for one resource (inside top10_by_calls) |
| `kaynak` | `resource` | string | resource identifier, truncated to 120 characters |

#### Sherlock leaderboard

*Cumulative lifetime payouts per security researcher. There is no date parameter upstream — this is a running total, not a period figure.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `arastirmaci_sayisi` | `researcher_count` | integer | researchers listed on the leaderboard |
| `odemeli_kayit` | `records_with_payout` | integer | how many of them have a numeric payout |
| `omur_boyu_odeme` | `lifetime_payout` | object (distribution) | distribution of lifetime earnings in USD |
| `top10` | `top10` | array | the ten largest entries (also used by Apify and Hugging Face) |
| `handle` | `handle` | string | researcher handle |
| `odeme` | `payout` | number (USD) | that researcher's lifetime payout |

#### DeFiLlama

*Two endpoints from DeFiLlama's fees dataset (fees paid by users, not protocol revenue): the AI-Agents category cross-section, and the daily fee series of one fixed protocol in it.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `ai_agent_protokol_sayisi` | `ai_agent_protocol_count` | integer | protocols DeFiLlama files under an AI-Agent category |
| `toplam_protokol` | `total_protocols` | integer | protocols in the whole fees dataset, for context |
| `ai_total24h` | `ai_total_24h` | number (USD) | summed 24h fees across AI-agent protocols |
| `ai_total24h_n` | `ai_total_24h_n` | integer | how many protocols contributed a number to that sum |
| `ai_total7d` | `ai_total_7d` | number (USD) | summed 7-day fees |
| `ai_total7d_n` | `ai_total_7d_n` | integer | how many protocols contributed |
| `ai_total30d` | `ai_total_30d` | number (USD) | summed 30-day fees |
| `ai_total30d_n` | `ai_total_30d_n` | integer | how many protocols contributed |
| `ai_top5_30d` | `ai_top5_30d` | array | five largest AI-agent protocols by 30-day fees |
| `ad` | `name` | string | protocol name (inside ai_top5_30d) |
| `usd30d` | `usd_30d` | number (USD) | that protocol's 30-day fees |
| `ai_30g_dagilim` | `ai_30d_distribution` | object (distribution) | distribution of 30-day fees across AI-agent protocols — where concentration becomes visible |
| `protokol` | `protocol` | string | the single protocol tracked in detail |
| `gun_sayisi` | `day_count` | integer | days available in that protocol's daily series |
| `total24h` | `total_24h` | number (USD) | protocol fees, last 24h |
| `total7d` | `total_7d` | number (USD) | protocol fees, last 7 days |
| `total30d` | `total_30d` | number (USD) | protocol fees, last 30 days |
| `totalAllTime` | `total_all_time` | number (USD) | protocol fees, all time |
| `ilk_gun_utc` | `first_day_utc` | string (date) | first day present in the daily series |
| `son_gun_utc` | `last_day_utc` | string (date) | last day present in the daily series |
| `son30g_dagilim` | `last_30d_distribution` | object (distribution) | distribution of the protocol's daily fees over the last 30 days |

#### Apify store

*Published automation actors. SAMPLED: top 1,000 by popularity, which is an upper tier and explicitly not the store median. About 83-87 % of the sampled actors carry a numeric user count; `scanned` gives the exact number that entered the distribution.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `magaza_toplam_aktor` | `store_total_actors` | integer | total actors the store reports |
| `toplam_kullanici_dagilimi` | `total_users_distribution` | object (distribution) | distribution of users per actor across the sample |
| `aktor` | `actor` | string | actor identifier as username/name |
| `kullanici` | `users` | integer | that actor's total users |

#### Hugging Face

*Top 100 models by download count. `downloads` is the count the source reports for its recent window, not a cumulative total, so a model's value can fall from one run to the next; there is no official historical endpoint — this series is the archive.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `model_sayisi` | `model_count` | integer | models in the sample |
| `indirme_dagilimi` | `download_distribution` | object (distribution) | distribution of the models' downloads across the sample (the count the source reports for its recent window, not a cumulative total) |
| `indirme` | `downloads` | integer | that model's downloads: the count the source reports for its recent window, not a cumulative total; it can fall from one run to the next |
| `begeni` | `likes` | integer | that model's like count |

#### npm downloads

*Per-package download volume. The upstream clips the range to roughly 547 days, so old data falls off and must be archived.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `baslangic` | `range_start` | string (date) | first day of the returned range |
| `bitis` | `range_end` | string (date) | last day of the returned range |
| `gun` | `day_count` | integer | days returned in the range |
| `toplam_30g` | `downloads_30d` | integer | downloads summed over the returned 30-day range |
| `son_gun` | `last_day` | object | the final day's raw record, kept as a spot check |
| `downloads` | `downloads` | integer | downloads on that day (upstream key, already English) |
| `day` | `day` | string (date) | the day itself (upstream key, already English) |

#### PyPI downloads

*Per-package download volume excluding mirror traffic. The upstream window is roughly 183 days (about six months), so old data falls off. `non_mirror_total` is the sum over that rolling window, not an all-time total.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `kayit` | `records` | integer | rows returned for the package |
| `aynasiz_gun` | `non_mirror_days` | integer | rows in the without_mirrors category |
| `ilk_tarih` | `first_date` | string (date) | earliest date in the returned window |
| `son_tarih` | `last_date` | string (date) | latest date in the returned window |
| `aynasiz_toplam` | `non_mirror_total` | integer | total non-mirror downloads across the window |
| `aynasiz_son30g` | `non_mirror_last_30d` | integer | non-mirror downloads over the last 30 days of the window |

#### GitHub repositories

*Point-in-time snapshot of agent-framework repositories. GitHub exposes no historical star series here, so each run is one archived point.*

| key (as published) | English | type | what it measures |
|---|---|---|---|
| `yildiz` | `stars` | integer | stargazer count |
| `catal` | `forks` | integer | fork count |
| `izleyen` | `watchers` | integer | subscriber/watcher count |
| `acik_konu` | `open_issues` | integer | open issues (GitHub counts pull requests here too) |
| `son_push` | `last_push` | string (ISO-8601, UTC) | most recent push to the default branch |

#### Keys that are data, not schema

Two kinds of key are generated at runtime and are copied through unchanged:

- **Histogram buckets** — Every direct child of a `histogram` object is a numeric bucket label produced at runtime (e.g. "<1", "1-10", ">=10000"). These are DATA, not schema, and are copied through unchanged.  
  Examples: `<1`, `1-10`, `100-1000`, `>=10000`, `100000-1e+06`
- **Package / repository identifiers** — For the endpoints listed below, every direct child of `ozet` is a package or repository identifier chosen at runtime. These are DATA, not schema, and are copied through unchanged.  
  Endpoints: `npm_downloads`, `pypi_downloads`, `github_repos`  
  Examples: `@anthropic-ai/sdk`, `anthropic`, `langchain-ai/langchain`, `Significant-Gravitas/AutoGPT`

### Why the keys stay Turkish

The series is **append-only** and each commit's file is OpenTimestamps-stamped. Renaming the keys in
place would make every earlier line unreadable and put two schemas in one file — which is data
corruption dressed up as tidying. So the keys are **frozen for series continuity**, the map above is
maintained as the English contract, and an **English-keyed mirror is generated instead**:

```bash
python3 to_english.py --english        # reads the frozen series, writes series-en.ndjson
python3 to_english.py --self-test      # proves the map is complete and strict
```

[`series-en.ndjson`](series-en.ndjson) is committed alongside the original, so you can use
English keys today without the original series ever being rewritten.

The converter **fails loudly** rather than guessing: any key that is neither in the map nor covered
by an explicit passthrough rule aborts the run and prints what was missed. A silently dropped key is
how a schema change becomes invisible — the exact failure this project exists to catch.

A fully English-keyed series (`v1.0`) is planned as a **separate, parallel series** with its own
first stamp, not as a rewrite of this one.

### Language

User-facing output is English: module docstrings, `--help` text, printed lines, and the record
annotations written from 2026-08-18 onward. **Internal identifiers inside the Python collectors
remain Turkish** (function and variable names such as `dagilim_ozeti`, `TASIYICILAR`), as do the
published JSON keys. Renaming them would be churn without benefit; the map above and the comments
carry the meaning.

---

### Known limits (stated, not hidden)

1. **Summaries only.** Raw API payloads are not stored (size); a `bayt` field records payload size for control.
2. **Sampling where the source paginates.** Apify: top 1,000 of the store (47,257 on 2026-08-18) by popularity, of which about 835–870 per run
   carry a numeric user count (`taranan` / `scanned` gives the exact number). Hugging Face: top 100.
   These are **upper-tier samples, not medians** — treat them as such.
3. **Schema fragility.** If an endpoint changes shape, a naive reader returns 0 silently. This happened to us
   on day one (`contests` vs `items`), which is why the freshness watchdog checks for silent zeros, frozen
   counters, missing endpoints and open-window listings whose newest entry is months old — not just staleness.
4. **Eleven endpoints is not the supply side.** It is eleven measurable corners of it. Coverage will be stated
   with every expansion.
5. **Short history.** The series starts on 2026-08-18. Its value compounds; it does not
   start high.
6. **The watchdog guards all 11 of the 11 endpoints.** `code4rena_audits` joined the watchdog's table with
   `yarisma_sayisi` (total audits listed) as its load-bearing number, derived from the 23 OK runs that carry
   it up to 2026-09-28: it was never 0 and never fell, so a silent zero or a drop is caught. It stayed at 475
   for all 41 days, so, like `sherlock_contests`, it is a slow counter and the frozen check reports it as
   YELLOW until it moves. The frozen thresholds and carriers were re-derived from the 28 runs up to
   2026-09-28; the Hugging Face and DeFiLlama category carriers are now the summed downloads and the summed
   30-day fees, which move with every run.
7. **`cantina_competitions` is implemented and measured but not yet wired in.** It is present in
   `collector.py` and deliberately absent from the active endpoint list, so it produces no rows.
8. **One reordering in the first week.** When the rows of the second collector were merged on 2026-08-24,
   the 24 rows published on 2026-08-18 were kept but their order within each run changed, so the
   2026-08-18 file is not a byte prefix of later files. Every publication since then extends the previous
   one unchanged, and the watchdog now checks this against the newest snapshot under `archive/`.

---

## Using the series

One run is all rows sharing a `zaman_utc`. Some days carry more than one run (see *Method*), and a row can
be incomplete, so pick rows before building a time series:

- use rows with `durum == "OK"` only;
- treat a summary that carries `olculemedi`, or a per-package sub-summary that carries `hata` or
  `olculemedi`, as missing data — never as a measured zero;
- for a weekly series, keep the last usable row per endpoint and ISO week.

A runnable version that prints one value per endpoint and week, with gaps shown as `GAP`, is
[`examples/weekly_series.py`](examples/weekly_series.py) (`python3 examples/weekly_series.py --help`).

```python
import json
from datetime import datetime

rows = [json.loads(line) for line in open("ai-arz-serisi.ndjson", encoding="utf-8") if line.strip()]

def usable(r):
    o = r.get("ozet")
    if r.get("durum") != "OK" or not isinstance(o, dict) or "olculemedi" in o:
        return False
    return not any(isinstance(v, dict) and ("hata" in v or "olculemedi" in v) for v in o.values())

latest = {}
for r in rows:
    if usable(r):
        year, week, _ = datetime.fromisoformat(r["zaman_utc"]).isocalendar()
        key = ("%d-W%02d" % (year, week), r["uc"])
        if key not in latest or r["zaman_utc"] > latest[key]["zaman_utc"]:
            latest[key] = dict(r, week=key[0])

weekly = sorted(latest.values(), key=lambda r: (r["week"], r["uc"]))
```

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

## Licensing

| what | licence | file |
|---|---|---|
| **Data** — `ai-arz-serisi.ndjson`, `series-en.ndjson`, `archive/`, `*.ots`, tables in this README | **CC BY 4.0** | `LICENSE-DATA` |
| **Code** — `collector.py`, `freshness_watchdog.py`, `run_weekly.sh`, `to_english.py`, `schema_map.json`, `tests/` | **MIT** | `LICENSE` |

Use the data freely, including commercially — attribution is the only condition.

## How to cite

```
AI Supply Index (2026). Weekly timestamped measurement of the AI economy's supply side.
mergenhq. https://github.com/mergenhq/ai-supply-index
— accessed YYYY-MM-DD, snapshot (for example) archive/ai-arz-serisi-20260928T074103Z.ndjson, sha256:171798127f984121…
```

Cite the newest snapshot under `archive/` at the time you accessed the data, with the first 16 hex characters
of its sha256 (`sha256sum archive/<file>`); that snapshot's `.ots` proof sits next to it.

A single citation format is deliberate: it makes attribution countable, which is the
only way this series can be evaluated as a track record rather than as a claim.

## Reproduce it

```bash
python3 collector.py --out my-run.ndjson  # one run, ~100 s, 11 endpoints, no credentials; exit 0=all OK 3=partial 1=none
python3 freshness_watchdog.py             # audit the series: 0=green 1=yellow 2=red
python3 to_english.py --english           # English-keyed mirror -> series-en.ndjson
```

Without `--out`, `collector.py` appends to `ai-arz-serisi.ndjson` itself, and your copy then no longer
matches the published, stamped file.

| file | what it is |
|---|---|
| [`ai-arz-serisi.ndjson`](ai-arz-serisi.ndjson) | the raw series, append-only, keys frozen |
| [`series-en.ndjson`](series-en.ndjson) | the same data with English keys, generated |
| [`collector.py`](collector.py) | the collector, 11 endpoints |
| [`freshness_watchdog.py`](freshness_watchdog.py) | the consumer that catches silent zeros |
| [`run_weekly.sh`](run_weekly.sh) | collect → stamp → audit, as cron runs it; exit 1 = nothing collected, 2 = watchdog red, 3 = partial |
| [`schema_map.json`](schema_map.json) | the key contract, source of the Schema table |
| [`to_english.py`](to_english.py) | mirror generator + schema-table generator |

Tests: `python3 -m pytest -q` runs the suite under `tests/` (no network, no writes outside a temporary
directory). `freshness_watchdog.py --self-test` and `to_english.py --self-test` are built-in self-tests.

---

*Corrections welcome. If a number here is wrong, open an issue with the endpoint and the counter-measurement;
it will be fixed in the next weekly run and the correction recorded in the series.*
