# Using the English-keyed mirror

`series-en.ndjson` holds the same rows as `ai-arz-serisi.ndjson`, with every key translated
through `schema_map.json`. Only keys change; values do not. This guide shows how to apply the
selection rules from the README section "Using the series" to the mirror, and which English keys
hold the weekly value of each endpoint. The code below gives the same weekly values as
`examples/weekly_series.py` gives on the Turkish-keyed file; `tests/test_english_mirror_guide.py`
runs it and checks that.

## Keys and values you need

| Turkish key | English key | note |
|---|---|---|
| `zaman_utc` | `timestamp_utc` | one run = all rows with the same value |
| `uc` | `endpoint` | the endpoint names themselves are unchanged, e.g. `x402_discovery` |
| `durum` | `status` | values are unchanged: `OK`, `HATA`, `HTTP-HATA`, `HATA-ICERIDE` |
| `ozet` | `summary` | the measurement |
| `olculemedi` | `unmeasurable` | present only when the measurement is incomplete |
| `hata` | `error` | inside a per-package sub-summary: that package failed |

Package and repository names under `summary` (npm, PyPI, GitHub) and histogram bucket labels are
data, so they are copied unchanged.

## The rules, in English keys

- use rows with `status == "OK"` only;
- treat a `summary` that carries `unmeasurable`, or a per-package sub-summary that carries `error`
  or `unmeasurable`, as missing data, never as a measured zero;
- for a weekly series, keep the last usable row per endpoint and ISO week.

## Where the weekly value is

| endpoint | English path in `summary` |
|---|---|
| `x402_discovery` | `resource_count` |
| `sherlock_leaderboard` | `researcher_count` |
| `sherlock_contests` | `open_count` |
| `code4rena_audits` | `open_count` |
| `defillama_fees_ai_agents` | `ai_total_30d` |
| `defillama_summary_virtuals` | `total_30d` |
| `apify_store` | `store_total_actors` |
| `hf_models` | `download_distribution.total` |
| `npm_downloads` | sum of `downloads_30d` over the packages |
| `pypi_downloads` | sum of `non_mirror_total` over the packages |
| `github_repos` | sum of `stars` over the repositories |

## Weekly values from the mirror, standard library only

```python
import json
from datetime import datetime

PATHS = {
    "x402_discovery": ["resource_count"], "sherlock_leaderboard": ["researcher_count"],
    "sherlock_contests": ["open_count"], "code4rena_audits": ["open_count"],
    "defillama_fees_ai_agents": ["ai_total_30d"], "defillama_summary_virtuals": ["total_30d"],
    "apify_store": ["store_total_actors"], "hf_models": ["download_distribution", "total"],
}
PER_PACKAGE = {"npm_downloads": "downloads_30d", "pypi_downloads": "non_mirror_total",
               "github_repos": "stars"}


def number(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def weekly_value(row):
    """The row's value, or None when the README rules make it missing data."""
    s = row.get("summary")
    if row.get("status") != "OK" or not isinstance(s, dict) or "unmeasurable" in s:
        return None
    if any(isinstance(v, dict) and ("error" in v or "unmeasurable" in v) for v in s.values()):
        return None
    if row["endpoint"] in PER_PACKAGE:
        found = [number(v.get(PER_PACKAGE[row["endpoint"]])) for v in s.values() if isinstance(v, dict)]
        found = [x for x in found if x is not None]
        return sum(found) if found else None
    v = s
    for key in PATHS.get(row["endpoint"], [None]):
        v = v.get(key) if isinstance(v, dict) else None
    return number(v)


rows = [json.loads(line) for line in open("series-en.ndjson", encoding="utf-8") if line.strip()]
latest = {}
for r in rows:
    value = weekly_value(r)
    if value is None:
        continue
    year, week, _ = datetime.fromisoformat(r["timestamp_utc"]).isocalendar()
    key = ("%d-W%02d" % (year, week), r["endpoint"])
    if key not in latest or r["timestamp_utc"] > latest[key]["timestamp_utc"]:
        latest[key] = {"week": key[0], "endpoint": r["endpoint"], "value": value,
                       "timestamp_utc": r["timestamp_utc"]}

weekly = sorted(latest.values(), key=lambda e: (e["week"], e["endpoint"]))
```

A week that has no entry in `weekly` for an endpoint has no usable value: report it as a gap,
not as 0. `examples/weekly_series.py` lists those gaps with their reason.
