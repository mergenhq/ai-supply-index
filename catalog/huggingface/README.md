---
license: cc-by-4.0
pretty_name: AI Supply Index
tags:
- ai-economy
- supply-side
- weekly
- time-series
configs:
- config_name: series-en
  data_files: series-en.ndjson
  default: true
- config_name: ai-arz-serisi
  data_files: ai-arz-serisi.ndjson
---

# AI Supply Index

**A weekly, timestamped, independently collected record of the *supply side* of the AI economy.**

| file | what it is |
|---|---|
| `ai-arz-serisi.ndjson` | the raw series, append-only, keys frozen |
| `series-en.ndjson` | the same data with English keys, generated |
| `schema_map.json` | the key contract, source of the Schema table |

Method, schema and how to read the series: https://github.com/mergenhq/ai-supply-index

## Known limits

See [Known limits (stated, not hidden)](https://github.com/mergenhq/ai-supply-index#known-limits-stated-not-hidden) in the repository README.

## Conflict of interest

The author operates automated trading systems on prediction markets (Kalshi, Hyperliquid, Polymarket),
and is therefore **not a neutral party** with respect to the economics of AI-driven trading.
Two of the tracked endpoints (Sherlock, x402) are markets the author could plausibly participate in.

The defence offered here is not neutrality but **method transparency**: every number is reproducible from
the published collector and the raw series, and every limit above is stated before anyone asks.

Additionally: this measurement is produced with substantial AI assistance. An AI-assisted system measuring
the AI economy is itself a conflict worth naming.

## How to cite

```
AI Supply Index (2026). Weekly timestamped measurement of the AI economy's supply side.
mergenhq. https://github.com/mergenhq/ai-supply-index
— accessed YYYY-MM-DD, snapshot archive/ai-arz-serisi-20260928T074103Z.ndjson, sha256:171798127f984121…
```

Cite the newest snapshot under `archive/` at the time you accessed the data, with the first 16 hex characters
of its sha256 (`sha256sum archive/<file>`); that snapshot's `.ots` proof sits next to it.

A single citation format is deliberate: it makes attribution countable, which is the
only way this series can be evaluated as a track record rather than as a claim.

## Licence

Data (`ai-arz-serisi.ndjson`, `series-en.ndjson`): CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/legalcode

`schema_map.json`: MIT, as listed under Licensing in the repository README.
