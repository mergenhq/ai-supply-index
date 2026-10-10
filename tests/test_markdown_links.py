"""Every relative link in the repository's Markdown files points at a file or folder that exists, and
every #anchor matches a heading in the target file. Web links are not followed."""
import re
from pathlib import Path

import pytest

from conftest import KOK

DOSYALAR = sorted(p for p in KOK.rglob("*.md") if ".git" not in p.parts and "__pycache__" not in p.parts)
BAG = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def kod_disi(metin):
    """The text without fenced code blocks and inline code, where brackets are not links."""
    metin = re.sub(r"```.*?```", "", metin, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", metin)


def capa(baslik):
    """GitHub's anchor for a heading: lower case, punctuation removed, spaces become hyphens."""
    baslik = re.sub(r"[*_`]", "", baslik.strip().lower())
    return re.sub(r"[^\w\- ]", "", baslik).replace(" ", "-")


def capalar(yol):
    metin = re.sub(r"```.*?```", "", yol.read_text(encoding="utf-8"), flags=re.S)
    return {capa(h) for h in re.findall(r"^#{1,6} (.+?)\s*#*$", metin, flags=re.M)}


def baglar():
    out = []
    for d in DOSYALAR:
        for hedef in BAG.findall(kod_disi(d.read_text(encoding="utf-8"))):
            if not re.match(r"[a-z]+:", hedef):
                out.append((d, hedef))
    return out


BAGLAR = baglar()


def test_the_readme_has_relative_links():
    assert any(d.name == "README.md" and d.parent == KOK for d, _ in BAGLAR)


@pytest.mark.parametrize("dosya,hedef", BAGLAR, ids=["%s->%s" % (d.relative_to(KOK), h) for d, h in BAGLAR])
def test_relative_link_resolves(dosya, hedef):
    yol, _, parca = hedef.partition("#")
    hedef_yol = (dosya.parent / yol).resolve() if yol else dosya
    assert hedef_yol.exists(), "%s links to a missing %s" % (dosya.relative_to(KOK), hedef)
    assert KOK.resolve() in hedef_yol.resolve().parents or hedef_yol.resolve() == KOK.resolve()
    if parca:
        assert hedef_yol.suffix == ".md", hedef
        assert parca in capalar(hedef_yol), "%s: no heading for #%s" % (dosya.relative_to(KOK), parca)


def test_anchor_rule_matches_github_for_the_headings_in_use():
    assert capa("Schema") == "schema"
    assert capa("Known limits (stated, not hidden)") == "known-limits-stated-not-hidden"
    assert capa("First measurement — 2026-08-18") == "first-measurement--2026-08-18"
