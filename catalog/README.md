# Catalog metadata

Metadata for listing this dataset in data catalogues. Nothing here is generated or uploaded
automatically; the files are copied by hand when a listing is created or updated.

| file | catalogue | what it is for |
|---|---|---|
| [`../datapackage.json`](../datapackage.json) | any Frictionless Data Package reader | describes `ai-arz-serisi.ndjson`, `series-en.ndjson` and `schema_map.json` at the repository root |
| [`huggingface/README.md`](huggingface/README.md) | Hugging Face | the dataset card; upload it as `README.md` at the root of the dataset repository |

Files that go with each catalogue:

- **Hugging Face:** `huggingface/README.md` (as `README.md`), `ai-arz-serisi.ndjson`, `series-en.ndjson`,
  `schema_map.json`.
- **Frictionless:** `datapackage.json` is read from the repository root, where the three files it names live.

## What the owner replaces

Nothing. No file here holds a placeholder; the dataset card names no account.

## File names on upload

The Hugging Face loader reads `.ndjson` files as JSON Lines as they are, so the series files are uploaded
under their repository names and the `configs` in the card point at those names. Nothing is renamed.

## Citation

The citation in the dataset card is the one in "How to cite" in the repository [README](../README.md#how-to-cite).
It is the only citation format, on purpose: a single format makes attribution countable. If "How to cite"
changes, copy the new block into `huggingface/README.md`; no other citation file is kept.
