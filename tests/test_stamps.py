"""Tests for the published OpenTimestamps proofs and the README text that describes them.
Only files in the repository are read; nothing is verified against a calendar server."""
import hashlib
import re

import pytest

from conftest import KOK

BASLIK = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OP_SHA256 = 0x08


def ots_ozeti(yol):
    """The sha256 digest an .ots proof commits to (header, version byte, op, 32 bytes)."""
    b = yol.read_bytes()
    assert b.startswith(BASLIK), yol
    i = len(BASLIK) + 1
    assert b[i] == OP_SHA256, yol
    return b[i + 1:i + 33].hex()


def sha256(yol):
    return hashlib.sha256(yol.read_bytes()).hexdigest()


ARSIV_OTS = sorted((KOK / "archive").glob("*.ndjson.ots"))


@pytest.mark.parametrize("ots", ARSIV_OTS, ids=lambda p: p.name)
def test_each_archive_proof_stamps_its_sibling(ots):
    assert ots_ozeti(ots) == sha256(ots.with_suffix(""))


def test_latest_archive_is_the_published_series():
    son = sorted((KOK / "archive").glob("*.ndjson"))[-1]
    assert son.read_bytes() == (KOK / "ai-arz-serisi.ndjson").read_bytes()


def test_readme_citation_hash_is_a_stamped_archive_file():
    readme = (KOK / "README.md").read_text(encoding="utf-8")
    m = re.search(r"sha256:([0-9a-f]{16,64})", readme)
    assert m, "README has no sha256 citation example"
    eslesen = [o for o in ARSIV_OTS if ots_ozeti(o).startswith(m.group(1))]
    assert eslesen, "citation hash %s is not stamped by any archive/ proof" % m.group(1)
    assert eslesen[0].with_suffix("").name in readme


def test_readme_names_what_the_root_proof_stamps():
    ozet = ots_ozeti(KOK / "ai-arz-serisi.ndjson.ots")
    readme = (KOK / "README.md").read_text(encoding="utf-8")
    assert ozet[:16] in readme
