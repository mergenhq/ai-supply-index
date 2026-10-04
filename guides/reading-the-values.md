# Reading the values

The weekly tools in `examples/` reduce every endpoint to one number per ISO week (see
`VALUES` in `examples/weekly_series.py`). Those numbers are not all the same kind of
quantity. Some count what exists at the moment of the run, some sum a moving window, and
some are taken from a sample whose members change. Before you compare two weeks, check which
kind you have. The table below says what the weekly value is and what a change between two
weeks can and cannot tell you.

Every statement marked *(series)* was measured on the published `ai-arz-serisi.ndjson`
(2026-08-18 to 2026-09-28). `tests/test_reading_values_guide.py` checks those statements
against the file, so they stay true or the test fails.

## What the weekly value is

| endpoint | weekly value | kind of number | a change between two weeks means |
|---|---|---|---|
| `x402_discovery` | `kaynak_sayisi` | count of resources in the registry at run time | net additions minus removals; the count also falls in some weeks *(series)* |
| `sherlock_leaderboard` | `arastirmaci_sayisi` | count of researchers on the leaderboard at run time | new researchers on the board |
| `sherlock_contests` | `acik_yarisma` | contests open at run time | how many doors were open at that moment, not over the week |
| `code4rena_audits` | `acik_yarisma` | audits open at run time | as above |
| `defillama_fees_ai_agents` | `ai_total30d` | sum of 30-day fees over the protocols filed as AI Agent **at run time** | both the fees and the set of protocols move: 17, 18 and 19 protocols appear *(series)* |
| `defillama_summary_virtuals` | `total30d` | 30-day fees of one fixed protocol | a shift of a moving 30-day window, not fees earned that week |
| `apify_store` | `magaza_toplam_aktor` | actors in the store at run time | net growth of the store |
| `hf_models` | `indirme_dagilimi.toplam` | sum of `downloads` over the **current** top 100 models | membership of the top 100 changes, and a model's `downloads` falls between weeks *(series)*; read it as a moving window over a changing sample |
| `npm_downloads` | sum of `toplam_30g` | downloads over the last month per package (`gun` = 30 days in every row *(series)*) | a shift of a moving 30-day window |
| `pypi_downloads` | sum of `aynasiz_toplam` | non-mirror downloads over the upstream window (about 183 days *(series)*) | a shift of a moving half-year window; use `aynasiz_son30g` for the last 30 days |
| `github_repos` | sum of `yildiz` | stars at run time | net stars; a repository's stars also fall in some weeks *(series)* |

## Three things that are easy to get wrong

**A moving window is not a weekly flow.** For `npm_downloads`, `pypi_downloads`,
`defillama_*` and the `*_30g` distributions of `x402_discovery`, consecutive weeks share most
of their window. The difference between two weeks is the downloads or fees that entered the
window minus those that left it. It is not "what happened this week". Weekly values a week
apart overlap by about 23 of 30 days.

**A sample can change under you.** `hf_models` is the top 100 models by downloads at run time,
and `apify_store` distributions cover the top 1,000 actors by popularity. A model or actor that
enters or leaves the sample changes the total without anything growing. The `top10` lists stored
with these endpoints show who was in the sample at each run.

**"Open now" is a moment, not a week.** `acik_yarisma` counts what was open when the run
started. A contest that opened on Tuesday and closed on Thursday is never seen by runs on
Monday and Thursday mornings. The value has been 0 in every week of the published series
*(series)*. Read it together with "Known limits" in the README.

## Picking the right field for a question

| question | field | endpoint |
|---|---|---|
| How concentrated are fees among AI-agent protocols? | `ai_30g_dagilim.top1_pay` | `defillama_fees_ai_agents` |
| How many x402 resources are paid for at all? | `cagri_30g.sifir_sayisi`, `cagri_30g.n` | `x402_discovery` |
| What did the median Sherlock researcher earn over their lifetime? | `omur_boyu_odeme.p50` | `sherlock_leaderboard` |
| How fast is one SDK's download volume moving? | `toplam_30g` of that package | `npm_downloads` |
| Last-30-day PyPI downloads, not the half-year window | `aynasiz_son30g` | `pypi_downloads` |

Field meanings and types are in the README section "Schema" and in `schema_map.json`.
