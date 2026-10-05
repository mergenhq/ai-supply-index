"""The catalog metadata (datapackage.json and the files under catalog/) agrees with the repository:
every path it names exists, the licence matches LICENSE-DATA, the Hugging Face card repeats the README's
citation and conflict-of-interest text exactly, and no catalog file carries details that go stale or
identify a person. Standard library only; files are only read."""
import json
import re

import pytest

from conftest import KOK

CATALOG = KOK / "catalog"
DATAPACKAGE = KOK / "datapackage.json"
HF_CARD = CATALOG / "huggingface" / "README.md"
README = (KOK / "README.md").read_text(encoding="utf-8")


def catalog_files():
    return [DATAPACKAGE] + sorted(p for p in CATALOG.rglob("*") if p.is_file())


def section(text, heading):
    """Body of a '## ' section, without the horizontal rule that may close it."""
    start = text.index(heading + "\n") + len(heading) + 1
    end = text.find("\n## ", start)
    body = text[start:end if end != -1 else len(text)].strip()
    return re.sub(r"\n+---\s*$", "", body).strip()


def code_block(text):
    m = re.search(r"```\n(.*?)\n```", text, flags=re.S)
    assert m, "no code block"
    return m.group(1)


def licence_data_name():
    """'CC-BY-4.0' from the first line of LICENSE-DATA, e.g. '... (CC BY 4.0)'."""
    first = (KOK / "LICENSE-DATA").read_text(encoding="utf-8").splitlines()[0]
    m = re.search(r"\(([^)]+)\)\s*$", first)
    assert m, first
    return m.group(1).replace(" ", "-")


# ── Frictionless Data Package ──────────────────────────────────────────────
def test_datapackage_loads_and_every_path_exists():
    pkg = json.loads(DATAPACKAGE.read_text(encoding="utf-8"))
    assert pkg["resources"]
    for res in pkg["resources"]:
        assert (KOK / res["path"]).is_file(), res["path"]
        for lic in res.get("licenses", []):
            if not re.match(r"[a-z]+://", lic.get("path", "")):
                assert (KOK / lic["path"]).is_file(), lic["path"]


def test_datapackage_licence_is_cc_by_4_and_matches_licence_data():
    pkg = json.loads(DATAPACKAGE.read_text(encoding="utf-8"))
    assert [lic["name"] for lic in pkg["licenses"]] == ["CC-BY-4.0"]
    assert licence_data_name() == "CC-BY-4.0"


# ── Hugging Face dataset card ──────────────────────────────────────────────
def front_matter(text):
    """Parse the YAML front matter of the card (the subset it uses: scalars, lists of scalars and
    lists of flat mappings)."""
    assert text.startswith("---\n"), "no front matter"
    body = text[4:text.index("\n---\n", 4)]
    out, key, item = {}, None, None
    for line in body.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" ") and not line.startswith("-"):
            k, _, v = line.partition(":")
            assert _, "not a key: %r" % line
            key, item = k.strip(), None
            out[key] = v.strip() if v.strip() else []
        elif line.startswith("- "):
            k, sep, v = line[2:].partition(":")
            if sep and not v.startswith("/"):
                item = {k.strip(): v.strip()}
                out[key].append(item)
            else:
                out[key].append(line[2:].strip())
        else:
            k, sep, v = line.strip().partition(":")
            assert sep and isinstance(item, dict), "not a mapping entry: %r" % line
            item[k.strip()] = v.strip()
    return out


def test_card_front_matter_parses_with_cc_by_4_licence():
    meta = front_matter(HF_CARD.read_text(encoding="utf-8"))
    assert meta["license"] == "cc-by-4.0"
    assert meta["license"].upper() == licence_data_name()


def test_every_data_file_in_the_card_exists():
    meta = front_matter(HF_CARD.read_text(encoding="utf-8"))
    paths = [c["data_files"] for c in meta["configs"]]
    assert paths
    for p in paths:
        assert (KOK / p).is_file(), p


def test_card_citation_block_equals_the_readme_block():
    card = HF_CARD.read_text(encoding="utf-8")
    assert code_block(section(card, "## How to cite")) == code_block(section(README, "## How to cite"))


def test_card_conflict_of_interest_equals_the_readme_section():
    card = HF_CARD.read_text(encoding="utf-8")
    assert section(card, "## Conflict of interest") == section(README, "## Conflict of interest")


# ── no Kaggle files ────────────────────────────────────────────────────────
def test_no_kaggle_file_in_catalog():
    kaggle = [p.relative_to(KOK).as_posix() for p in CATALOG.rglob("*")
              if "kaggle" in p.as_posix().lower() or p.name == "dataset-metadata.json"]
    assert kaggle == [], kaggle


# ── nothing that goes stale or identifies a person ────────────────────────
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ROW_COUNT = re.compile(r"\b\d[\d,]*\s+(?:rows|records|lines)\b", re.I)
FILE_SIZE = re.compile(r"\b\d[\d,.]*\s*(?:bytes|[KMG]i?B)\b")
HASH = re.compile(r"\b(?:sha(?:1|256|512)|md5):?[0-9a-f]{8,}|\b[0-9a-f]{16,}\b", re.I)
SNAPSHOT = re.compile(r"ai-arz-serisi-\d{8}T\d{6}Z")
STALE_KEYS = {"bytes", "hash", "sha256", "md5", "rows", "numRows", "rowCount", "count", "size"}


def visible_text(path):
    """The file's text without the README citation block, which the card must repeat as it is."""
    text = path.read_text(encoding="utf-8")
    return text.replace(code_block(section(README, "## How to cite")), "")


def json_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from json_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from json_keys(v)


@pytest.mark.parametrize("path", catalog_files(), ids=lambda p: p.relative_to(KOK).as_posix())
def test_catalog_file_has_no_email_row_count_size_hash_or_snapshot_name(path):
    text = visible_text(path)
    for name, pattern in (("e-mail address", EMAIL), ("row count", ROW_COUNT), ("file size", FILE_SIZE),
                          ("hash", HASH), ("snapshot name", SNAPSHOT)):
        m = pattern.search(text)
        assert not m, "%s in %s: %r" % (name, path.name, m.group(0))
    if path.suffix == ".json":
        assert not set(json_keys(json.loads(text))) & STALE_KEYS
