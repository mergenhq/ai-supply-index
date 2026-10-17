#!/usr/bin/env python3
"""snapshots.py — the frozen snapshots under archive/, their proofs, and how a copy relates to them.

Each publication copies the series to archive/ai-arz-serisi-<UTC stamp>.ndjson and stamps that
copy with OpenTimestamps (<same name>.ots); see "Method" in README.md. This lists every snapshot
with its row count, last run, sha256 and what its proof says, and then checks one file (by default
the published ai-arz-serisi.ndjson, or a copy you downloaded) against them:

  identical to    the snapshot whose bytes are exactly the file's bytes, if any
  extends         the newest snapshot the file begins with, byte for byte (the series is
                  append-only, so a later copy extends every earlier snapshot)
  added runs      the runs (zaman_utc, number of rows) after that snapshot

Proof checks are offline only: the sha256 digest a proof commits to is read from the .ots header
and compared with the snapshot's sha256, and the attestations in the proof are counted as
"pending" (submitted to a calendar server, not yet anchored) or "bitcoin" (anchored in a block).
Nothing is sent to a calendar server or a Bitcoin node; use `ots verify` for the full check.

Standard library only. Usage:
    python3 examples/snapshots.py
    python3 examples/snapshots.py --file my-copy.ndjson --json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "ai-arz-serisi.ndjson"
DEFAULT_ARCHIVE = ROOT / "archive"

OTS_HEADER = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OP_SHA256 = 0x08
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")
BITCOIN_TAG = bytes.fromhex("0588960d73d71901")


def proof_info(path):
    """{"digest": hex or None, "pending": n, "bitcoin": n, "error": text or None} for one .ots file."""
    b = Path(path).read_bytes()
    info = {"digest": None, "pending": b.count(PENDING_TAG), "bitcoin": b.count(BITCOIN_TAG), "error": None}
    i = len(OTS_HEADER) + 1                       # header, then one version byte
    if not b.startswith(OTS_HEADER):
        info["error"] = "not an OpenTimestamps proof"
    elif len(b) < i + 33 or b[i] != OP_SHA256:
        info["error"] = "proof does not start with a sha256 file digest"
    else:
        info["digest"] = b[i + 1:i + 33].hex()
    return info


def _runs(data):
    """[(zaman_utc, rows)] in file order for NDJSON bytes; lines that do not parse are skipped."""
    out = []
    for line in data.decode("utf-8").splitlines():
        try:
            stamp = json.loads(line).get("zaman_utc")
        except (ValueError, AttributeError):
            continue
        if out and out[-1][0] == stamp:
            out[-1] = (stamp, out[-1][1] + 1)
        else:
            out.append((stamp, 1))
    return out


def snapshot_list(archive):
    """One dict per snapshot in archive/, oldest first (names sort by their UTC stamp)."""
    out = []
    for p in sorted(Path(archive).glob("ai-arz-serisi-*.ndjson")):
        data = p.read_bytes()
        runs = _runs(data)
        sha = hashlib.sha256(data).hexdigest()
        proof_path = p.with_name(p.name + ".ots")
        entry = {"snapshot": p.name, "rows": sum(n for _, n in runs),
                 "last_run": runs[-1][0] if runs else None, "sha256": sha, "proof": None}
        if proof_path.exists():
            info = proof_info(proof_path)
            info["matches"] = info["digest"] == sha
            entry["proof"] = info
        out.append((entry, data))
    return out


def compare(file_path, snapshots):
    """How one file relates to the snapshots: identical_to, extends, added_runs, sha256, rows."""
    data = Path(file_path).read_bytes()
    report = {"file": str(file_path), "sha256": hashlib.sha256(data).hexdigest(),
              "rows": sum(n for _, n in _runs(data)), "identical_to": None, "extends": None, "added_runs": None}
    for entry, snap in snapshots:
        if data == snap:
            report["identical_to"] = entry["snapshot"]
        if data.startswith(snap):
            report["extends"] = entry["snapshot"]
            report["added_runs"] = [{"zaman_utc": s, "rows": n} for s, n in _runs(data[len(snap):])]
    return report


def _proof_text(proof):
    if proof is None:
        return "no proof"
    if proof["error"]:
        return "proof: %s" % proof["error"]
    state = ("bitcoin" if proof["bitcoin"] else "pending") + " (%d pending, %d bitcoin)" % (
        proof["pending"], proof["bitcoin"])
    return "proof %s, %s" % ("matches" if proof["matches"] else "DIGEST DIFFERS", state)


def _text(snaps, report):
    print("snapshots in archive/:")
    for e in snaps:
        print("  %-42s %4d rows  last run %s  sha256 %s…  %s" % (
            e["snapshot"], e["rows"], e["last_run"], e["sha256"][:16], _proof_text(e["proof"])))
    print()
    print("file: %s" % report["file"])
    print("  %d rows, sha256 %s…" % (report["rows"], report["sha256"][:16]))
    print("  identical to: %s" % (report["identical_to"] or "no snapshot"))
    if report["extends"] is None:
        print("  extends: no snapshot (the file does not begin with any snapshot byte for byte)")
        return
    print("  extends: %s" % report["extends"])
    added = report["added_runs"]
    print("  added runs after it: %s" % (len(added) or "none"))
    for r in added:
        print("    %s  %d rows" % (r["zaman_utc"], r["rows"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="List the frozen snapshots under archive/ with rows, last run, sha256 and an "
                    "offline check of their OpenTimestamps proofs (digest match; pending or bitcoin "
                    "attestations), then show which snapshot a file is identical to, which one it "
                    "extends byte for byte, and which runs were added after it.")
    ap.add_argument("--file", default=str(DEFAULT_FILE),
                    help="the series file to check (default: ai-arz-serisi.ndjson in the repository)")
    ap.add_argument("--archive", default=str(DEFAULT_ARCHIVE),
                    help="the directory with the snapshots (default: archive/ in the repository)")
    ap.add_argument("--json", action="store_true", help="print the full report as one JSON object")
    a = ap.parse_args(argv)

    try:
        pairs = snapshot_list(a.archive)
        report = compare(a.file, pairs)
    except (OSError, UnicodeDecodeError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    snaps = [e for e, _ in pairs]
    if a.json:
        print(json.dumps({"snapshots": snaps, "file": report}, ensure_ascii=False, indent=1))
    else:
        _text(snaps, report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
