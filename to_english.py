#!/usr/bin/env python3
"""to_english.py — generate an English-keyed mirror of the AI Supply Index series.

WHY THIS EXISTS
    The published series (`ai-arz-serisi.ndjson`) is append-only and OpenTimestamps-stamped,
    and its keys are Turkish. Renaming those keys in place would make every earlier line
    unreadable and put two schemas in one file — so the keys stay FROZEN.
    This tool does the safe thing instead: it READS the frozen series and WRITES a separate
    English-keyed mirror (`series-en.ndjson`). Nothing is modified, nothing is re-stamped,
    and an English-speaking consumer gets usable data today.

CONTRACT (the reason this is not a one-line dict comprehension)
    Every key must be accounted for. A key that is neither in the map nor covered by an
    explicit passthrough rule raises an error and the run FAILS. Silently dropping or
    silently passing through an unknown key is exactly how a schema change becomes invisible,
    which is the same failure mode the freshness watchdog exists to prevent.

USAGE
    python3 to_english.py --english                    # write series-en.ndjson
    python3 to_english.py --english --out other.ndjson # choose the output path
    python3 to_english.py --self-test                  # prove the mapping is complete + strict
    python3 to_english.py --schema-md                  # print the README Schema tables
"""
import argparse
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
VARSAYILAN_SERI = KOK / "ai-arz-serisi.ndjson"
VARSAYILAN_CIKTI = KOK / "series-en.ndjson"
HARITA = KOK / "schema_map.json"


class SemaBoslugu(Exception):
    """An key appeared that the map does not cover. Never swallowed."""


class AdCakismasi(Exception):
    """Two different keys in one object would collapse onto the same English name."""


def harita_yukle(yol=HARITA):
    m = json.loads(Path(yol).read_text(encoding="utf-8"))
    keys, kaynak = {}, {}
    for grup in m["groups"]:
        for satir in grup["keys"]:
            tr, en = satir[0], satir[1]
            if tr in keys:
                raise ValueError("duplicate Turkish key in map: %r (groups %r and %r)"
                                 % (tr, kaynak[tr], grup["name"]))
            if not en or not isinstance(en, str):
                raise ValueError("empty English name for key %r" % tr)
            keys[tr] = en
            kaynak[tr] = grup["name"]
    return m, keys


def _veri_anahtari(k, uc, yol, meta):
    """True when this key is runtime DATA (a bucket label or a package id), not schema."""
    if yol and yol[-1] == "histogram":
        return True
    if yol == ["ozet"] and uc in meta["passthrough"]["package_identifiers"]["endpoints"]:
        return True
    return False


def cevir(dugum, uc, yol, keys, meta, eksikler):
    if isinstance(dugum, dict):
        out, gorulen = {}, {}
        for k, v in dugum.items():
            if _veri_anahtari(k, uc, yol, meta):
                yeni = k
            elif k in keys:
                yeni = keys[k]
            else:
                eksikler.append({"key": k, "endpoint": uc, "path": "/".join(yol) or "<root>"})
                yeni = k
            if yeni in gorulen and gorulen[yeni] != k:
                raise AdCakismasi(
                    "keys %r and %r both map to %r inside %s (endpoint %s) — data would be lost"
                    % (gorulen[yeni], k, yeni, "/".join(yol) or "<root>", uc))
            gorulen[yeni] = k
            out[yeni] = cevir(v, uc, yol + [k], keys, meta, eksikler)
        return out
    if isinstance(dugum, list):
        return [cevir(x, uc, yol, keys, meta, eksikler) for x in dugum]
    return dugum


def seriyi_cevir(seri: Path, keys, meta):
    """Returns (converted_rows, missing_keys). Raises nothing for missing — the caller decides."""
    satirlar, eksikler = [], []
    for ham in Path(seri).read_text(encoding="utf-8").splitlines():
        ham = ham.strip()
        if not ham:
            continue
        r = json.loads(ham)
        satirlar.append(cevir(r, r.get("uc", "?"), [], keys, meta, eksikler))
    return satirlar, eksikler


def ingilizce_yaz(seri: Path, cikti: Path, keys, meta):
    satirlar, eksikler = seriyi_cevir(seri, keys, meta)
    if eksikler:
        benzersiz = sorted({(e["key"], e["endpoint"], e["path"]) for e in eksikler})
        print("SCHEMA GAP — %d unmapped key(s); refusing to write a half-translated mirror:"
              % len(benzersiz), file=sys.stderr)
        for k, uc, p in benzersiz:
            print("   key=%-28s endpoint=%-28s path=%s" % (k, uc, p), file=sys.stderr)
        print("\nAdd them to schema_map.json (or to a passthrough rule) and re-run.", file=sys.stderr)
        raise SemaBoslugu("%d unmapped key(s)" % len(benzersiz))
    with open(cikti, "w", encoding="utf-8") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print("written: %s  (%d rows, %d keys mapped, 0 unmapped)" % (cikti, len(satirlar), len(keys)))
    return 0


# ═════════════════════════════════════════════════════════════════════════════
# SELF-TEST — the converter is pointed at itself before it is trusted
# ═════════════════════════════════════════════════════════════════════════════
def _yapraklar(o, acc):
    """Collect every leaf value, so we can prove conversion loses nothing."""
    if isinstance(o, dict):
        for v in o.values():
            _yapraklar(v, acc)
    elif isinstance(o, list):
        for v in o:
            _yapraklar(v, acc)
    else:
        acc.append(o)
    return acc


def oz_test(seri: Path):
    meta, keys = harita_yukle()
    gecti = kaldi = 0

    def kontrol(ad, kosul, ayrinti=""):
        nonlocal gecti, kaldi
        gecti += bool(kosul)
        kaldi += (not kosul)
        print("  [%s] %s%s" % ("PASS" if kosul else "FAIL", ad,
                               ("  — " + ayrinti) if ayrinti else ""))
        return bool(kosul)

    print("SELF-TEST — to_english.py")
    print()

    # 1) the map itself is well formed (harita_yukle already rejects duplicates/empties)
    kontrol("map loads, no duplicate keys, no empty targets", True, "%d keys" % len(keys))
    kontrol("declared key_count matches the map",
            meta["_meta"]["key_count"] == len(keys),
            "declared=%s actual=%d" % (meta["_meta"]["key_count"], len(keys)))

    # 2) every English name is a plausible identifier (no leftover Turkish diacritics)
    kotu = [v for v in keys.values() if any(ch in v for ch in "çğıöşüÇĞİÖŞÜ") or " " in v]
    kontrol("English names contain no Turkish characters or spaces", not kotu, str(kotu[:5]))

    # 3) the real series converts with ZERO unmapped keys
    satirlar, eksikler = seriyi_cevir(seri, keys, meta)
    kontrol("real series converts with 0 unmapped keys",
            not eksikler,
            "rows=%d unmapped=%d %s" % (len(satirlar), len(eksikler),
                                        sorted({e["key"] for e in eksikler})[:6]))

    # 4) conversion loses nothing: same row count, same leaf values
    ham = [json.loads(x) for x in Path(seri).read_text(encoding="utf-8").splitlines() if x.strip()]
    kontrol("row count preserved", len(ham) == len(satirlar),
            "%d -> %d" % (len(ham), len(satirlar)))
    once = sorted(map(repr, _yapraklar(ham, [])))
    sonra = sorted(map(repr, _yapraklar(satirlar, [])))
    kontrol("every leaf value preserved", once == sonra,
            "%d leaves" % len(once))

    # 5) THE IMPORTANT ONE: an unknown key must FAIL, not be silently passed through
    sahte = {"zaman_utc": "2026-01-01T00:00:00+00:00", "uc": "x402_discovery",
             "ozet": {"kaynak_sayisi": 1, "bilinmeyen_alan": 42}}
    e2 = []
    cevir(sahte, "x402_discovery", [], keys, meta, e2)
    kontrol("unknown key is REPORTED (never silently skipped)",
            [e["key"] for e in e2] == ["bilinmeyen_alan"], str(e2))

    tmp = Path(__import__("tempfile").mkdtemp(prefix="ai-supply-en-")) / "bad.ndjson"
    tmp.write_text(json.dumps(sahte, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        ingilizce_yaz(tmp, tmp.with_suffix(".out"), keys, meta)
        kontrol("unknown key makes the run FAIL", False, "no exception raised")
    except SemaBoslugu:
        kontrol("unknown key makes the run FAIL", True, "SemaBoslugu raised, no file written")
    kontrol("no half-translated file left behind", not tmp.with_suffix(".out").exists())

    # 6) a name collision inside one object must FAIL (would silently drop a value)
    carpik = dict(keys)
    carpik["taranan"] = carpik["kaynak_sayisi"]          # force two keys onto one name
    try:
        cevir({"kaynak_sayisi": 1, "taranan": 2}, "x402_discovery", ["ozet"], carpik, meta, [])
        kontrol("name collision makes the run FAIL", False, "no exception raised")
    except AdCakismasi:
        kontrol("name collision makes the run FAIL", True, "AdCakismasi raised")

    # 7) passthrough rules work: histogram buckets and package ids survive verbatim
    h = cevir({"histogram": {"<1": 3, "1-10": 4, ">=10000": 1}}, "x402_discovery",
              ["ozet", "cagri_30g"], keys, meta, [])
    kontrol("histogram bucket labels pass through unchanged",
            sorted(h["histogram"]) == sorted(["<1", "1-10", ">=10000"]), str(h))
    p = cevir({"@anthropic-ai/sdk": {"toplam_30g": 5}}, "npm_downloads", ["ozet"], keys, meta, [])
    kontrol("package identifiers pass through, their children still map",
            "@anthropic-ai/sdk" in p and p["@anthropic-ai/sdk"] == {"downloads_30d": 5}, str(p))

    # 8) the silent-zero brake is documented, not just implemented
    kontrol("`olculemedi` maps to `unmeasurable`", keys.get("olculemedi") == "unmeasurable")

    # 9) the generated Markdown must not break out of its table cells
    #    (a description containing a raw "|" silently adds columns — caught in review once)
    bozuk_satir = []
    for ln in sema_md().splitlines():
        if not ln.startswith("| `"):
            continue
        if len(ln.replace("\\|", "").split("|")) - 1 != 5:
            bozuk_satir.append(ln[:80])
    kontrol("every generated table row has exactly 4 columns",
            not bozuk_satir, "%d malformed: %s" % (len(bozuk_satir), bozuk_satir[:2]))

    # 10) every key in the map appears exactly once in the generated table
    md = sema_md()
    eksik_md = [tr for tr in keys if ("| `%s` |" % tr) not in md]
    kontrol("every mapped key appears in the generated table",
            not eksik_md, str(eksik_md[:5]))

    print()
    print("SELF-TEST RESULT: %d passed / %d failed" % (gecti, kaldi))
    return 0 if kaldi == 0 else 1


def _hucre(s):
    """Escape a value so it cannot break out of a Markdown table cell."""
    return str(s).replace("|", "\\|")


def sema_md():
    meta, keys = harita_yukle()
    p = meta["passthrough"]
    out = []
    out.append("The series keys are Turkish and **frozen** — see *Why the keys stay Turkish* below.")
    out.append("This table is the contract. It is generated from [`schema_map.json`](schema_map.json)")
    out.append("via `python3 to_english.py --schema-md`, so the two cannot drift apart.")
    out.append("")
    for g in meta["groups"]:
        out.append("#### %s" % g["name"])
        out.append("")
        out.append("*%s*" % g["note"])
        out.append("")
        out.append("| key (as published) | English | type | what it measures |")
        out.append("|---|---|---|---|")
        for tr, en, tip, aciklama in g["keys"]:
            out.append("| `%s` | `%s` | %s | %s |"
                       % (tr, en, _hucre(tip), _hucre(aciklama)))
        out.append("")
    out.append("#### Keys that are data, not schema")
    out.append("")
    out.append("Two kinds of key are generated at runtime and are copied through unchanged:")
    out.append("")
    out.append("- **Histogram buckets** — %s  \n  Examples: %s"
               % (p["histogram_buckets"]["rule"],
                  ", ".join("`%s`" % x for x in p["histogram_buckets"]["examples"])))
    out.append("- **Package / repository identifiers** — %s  \n  Endpoints: %s  \n  Examples: %s"
               % (p["package_identifiers"]["rule"],
                  ", ".join("`%s`" % x for x in p["package_identifiers"]["endpoints"]),
                  ", ".join("`%s`" % x for x in p["package_identifiers"]["examples"])))
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description="Generate an English-keyed mirror of the AI Supply Index series. "
                    "The original series is never modified.")
    ap.add_argument("--series", default=str(VARSAYILAN_SERI),
                    help="the frozen Turkish-keyed series to read")
    ap.add_argument("--out", default=str(VARSAYILAN_CIKTI),
                    help="where to write the English-keyed mirror")
    ap.add_argument("--english", action="store_true",
                    help="write the English-keyed mirror")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="prove the map is complete and that unmapped keys FAIL the run")
    ap.add_argument("--schema-md", dest="schema_md", action="store_true",
                    help="print the Schema tables in Markdown (used to build README.md)")
    a = ap.parse_args()

    if a.self_test:
        return oz_test(Path(a.series))
    if a.schema_md:
        print(sema_md())
        return 0
    if a.english:
        meta, keys = harita_yukle()
        try:
            return ingilizce_yaz(Path(a.series), Path(a.out), keys, meta)
        except SemaBoslugu:
            return 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
