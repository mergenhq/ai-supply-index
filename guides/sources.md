# Where each number comes from

For every endpoint in the series this lists the public request `collector.py` makes, the upstream
fields it reads, and the keys it stores them under. A `%d` or `%s` in a URL is filled in by the
collector (a page offset or number, a package or repository name). All requests are
unauthenticated GETs. Raw responses are not stored, only the summaries (README, "Known limits").
`tests/test_sources_guide.py` checks every URL, list and key below against `collector.py` and
`schema_map.json`.

| endpoint | request | pages |
|---|---|---|
| `x402_discovery` | `https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=500&offset=%d` | until the reported total is reached or a page is empty; at most `X402_SAYFA_TAVANI` = 60 pages |
| `sherlock_leaderboard` | `https://mainnet-contest.sherlock.xyz/stats/leaderboard` | one request |
| `sherlock_contests` | `https://mainnet-contest.sherlock.xyz/contests?per_page=100&page=%d` | until `has_next` is false; at most `YARISMA_SAYFA_TAVANI` = 40 pages |
| `code4rena_audits` | `https://code4rena.com/api/v1/audits?page=%d` | until `nextPage` is empty; at most 40 pages |
| `defillama_fees_ai_agents` | `https://api.llama.fi/overview/fees?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true` | one request |
| `defillama_summary_virtuals` | `https://api.llama.fi/summary/fees/%s` with `LLAMA_PROTOKOL` = `virtuals-protocol` | one request |
| `apify_store` | `https://api.apify.com/v2/store?limit=100&offset=%d&sortBy=popularity` | 10 pages (the top 1,000 by popularity) |
| `hf_models` | `https://huggingface.co/api/models?sort=downloads&direction=-1&limit=100` | one request |
| `npm_downloads` | `https://api.npmjs.org/downloads/range/last-month/%s` | one request per package |
| `pypi_downloads` | `https://pypistats.org/api/packages/%s/overall` | one request per package, 2 s apart |
| `github_repos` | `https://api.github.com/repos/%s` | one request per repository |

`cantina_competitions` (`https://cantina.xyz/api/v0/competitions`) is implemented in
`collector.py` but not in the active endpoint list, so it writes no rows.

## Upstream field → stored key

- **x402_discovery**: `pagination.total` → `kaynak_sayisi`. For every resource,
  `quality.l30DaysTotalCalls` → distribution `cagri_30g` and `quality.l30DaysUniquePayers` →
  distribution `odeyen_30g`. The ten resources with the most calls (`resource`, calls) →
  `top10_cagri`.
- **sherlock_leaderboard**: the response maps each handle to its stats. The number of handles →
  `arastirmaci_sayisi`. Every numeric `payout` → distribution `omur_boyu_odeme` and `top10`.
- **sherlock_contests**: `total` → `yarisma_sayisi`. Contests with `ends_at` after the run →
  `acik_yarisma`, of which public ones (not `private`, `type_label` starting with "Public", not a bug
  bounty) → `acik_kamu`. The newest `starts_at` → `en_yeni_baslangic_utc`.
- **code4rena_audits**: `pagination.total` → `yarisma_sayisi`. Audits with `endTime` after the run →
  `acik_yarisma`, of which `codeAccess` = `public` → `acik_kamu`. The newest `startTime` →
  `en_yeni_baslangic_utc`.
- **defillama_fees_ai_agents**: protocols whose `category` contains "AI Agent". Their `total24h`,
  `total7d` and `total30d` are summed into `ai_total24h`, `ai_total7d` and `ai_total30d`. The five
  largest by `total30d` → `ai_top5_30d`, and the distribution of `total30d` → `ai_30g_dagilim`.
- **defillama_summary_virtuals**: `total24h`, `total7d`, `total30d` and `totalAllTime` are copied.
  The last 30 points of `totalDataChart` → distribution `son30g_dagilim`.
- **apify_store**: `data.total` → `magaza_toplam_aktor`. Each actor's `stats.totalUsers` →
  distribution `toplam_kullanici_dagilimi` and `top10`.
- **hf_models**: the number of models returned → `model_sayisi`. Each model's `downloads` →
  distribution `indirme_dagilimi` and `top10` (with `likes`).
- **npm_downloads**: per package, the daily `downloads` of the returned range are summed into
  `toplam_30g`. `start`, `end` and the number of days → `baslangic`, `bitis`, `gun`.
- **pypi_downloads**: per package, rows with `category` = `without_mirrors` are summed into
  `aynasiz_toplam`, and the last 30 of them into `aynasiz_son30g`.
- **github_repos**: per repository, `stargazers_count` → `yildiz`, `forks_count` → `catal`,
  `subscribers_count` → `izleyen`, `open_issues_count` → `acik_konu`, `pushed_at` → `son_push`.

## Packages and repositories tracked

- npm (`NPM_PAKETLER`): `@anthropic-ai/sdk`, `openai`, `langchain`, `@langchain/core`, `ai`,
  `@modelcontextprotocol/sdk`
- PyPI (`PYPI_PAKETLER`): `anthropic`, `openai`, `langchain`, `crewai`
- GitHub (`GH_DEPOLAR`): `langchain-ai/langchain`, `anthropics/anthropic-sdk-python`,
  `crewAIInc/crewAI`, `modelcontextprotocol/servers`, `Significant-Gravitas/AutoGPT`

Distributions are summarised by `dagilim_ozeti()` (see "Distribution summary" in the README
schema). What each stored key means is in the README "Schema" section and in `schema_map.json`.
