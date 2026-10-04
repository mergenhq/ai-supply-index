"""Tests for examples/snapshots.py — fixture snapshots and proofs under tmp_path; the published
files are only read. No calendar server or network is used."""
import hashlib
import importlib.util
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("snapshots", KOK / "examples" / "snapshots.py")
sn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sn)


def line(stamp, uc="x402_discovery"):
    return json.dumps({"zaman_utc": stamp, "uc": uc, "durum": "OK"}) + "\n"


R1 = line("2026-09-01T07:00:00+00:00") + line("2026-09-01T07:00:00+00:00", "apify_store")
R2 = line("2026-09-04T07:00:00+00:00")
R3 = line("2026-09-08T07:00:00+00:00") + line("2026-09-08T07:00:00+00:00", "hf_models")


def proof(data, pending=1, bitcoin=0, digest=None):
    d = bytes.fromhex(digest) if digest else hashlib.sha256(data).digest()
    return (sn.OTS_HEADER + b"\x01" + bytes([sn.OP_SHA256]) + d
            + (b"\x00" + sn.PENDING_TAG) * pending + (b"\x00" + sn.BITCOIN_TAG) * bitcoin)


def archive(tmp_path, snaps, proofs=None):
    """snaps: {stamp: text}; proofs: {stamp: bytes} (default: a matching pending proof)."""
    a = tmp_path / "archive"
    a.mkdir()
    for stamp, text in snaps.items():
        p = a / ("ai-arz-serisi-%s.ndjson" % stamp)
        p.write_text(text, encoding="utf-8")
        pr = (proofs or {}).get(stamp, proof(text.encode()))
        if pr is not None:
            (a / (p.name + ".ots")).write_bytes(pr)
    return a


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestProofInfo:
    def test_digest_and_attestations(self, tmp_path):
        p = tmp_path / "x.ots"
        p.write_bytes(proof(b"abc", pending=3, bitcoin=1))
        assert sn.proof_info(p) == {"digest": hashlib.sha256(b"abc").hexdigest(), "pending": 3, "bitcoin": 1,
                                    "error": None}

    @pytest.mark.parametrize("content, error", [
        (b"not a proof", "not an OpenTimestamps proof"),
        (sn.OTS_HEADER + b"\x01\x02" + b"\x00" * 32, "proof does not start with a sha256 file digest"),
        (sn.OTS_HEADER + b"\x01\x08\x00", "proof does not start with a sha256 file digest"),
    ])
    def test_unreadable_proof(self, tmp_path, content, error):
        p = tmp_path / "x.ots"
        p.write_bytes(content)
        assert sn.proof_info(p)["error"] == error and sn.proof_info(p)["digest"] is None


class TestSnapshotList:
    def test_rows_last_run_sha_and_matching_proof(self, tmp_path):
        a = archive(tmp_path, {"20260902T000000Z": R1})
        (entry, data), = sn.snapshot_list(a)
        assert entry["snapshot"] == "ai-arz-serisi-20260902T000000Z.ndjson" and data == R1.encode()
        assert (entry["rows"], entry["last_run"]) == (2, "2026-09-01T07:00:00+00:00")
        assert entry["sha256"] == hashlib.sha256(R1.encode()).hexdigest()
        assert entry["proof"]["matches"] is True and entry["proof"]["pending"] == 1

    def test_proof_for_other_bytes_does_not_match(self, tmp_path):
        a = archive(tmp_path, {"20260902T000000Z": R1}, {"20260902T000000Z": proof(b"other")})
        assert sn.snapshot_list(a)[0][0]["proof"]["matches"] is False

    def test_snapshot_without_proof(self, tmp_path):
        a = archive(tmp_path, {"20260902T000000Z": R1}, {"20260902T000000Z": None})
        assert sn.snapshot_list(a)[0][0]["proof"] is None

    def test_oldest_first(self, tmp_path):
        a = archive(tmp_path, {"20260909T000000Z": R1 + R2 + R3, "20260902T000000Z": R1})
        assert [e["rows"] for e, _ in sn.snapshot_list(a)] == [2, 5]


class TestCompare:
    def test_identical_to_the_newest_snapshot(self, tmp_path):
        a = archive(tmp_path, {"20260902T000000Z": R1, "20260905T000000Z": R1 + R2})
        r = sn.compare(write(tmp_path, "s.ndjson", R1 + R2), sn.snapshot_list(a))
        assert r["identical_to"] == r["extends"] == "ai-arz-serisi-20260905T000000Z.ndjson"
        assert r["added_runs"] == [] and r["rows"] == 3

    def test_later_copy_extends_the_newest_snapshot_and_lists_added_runs(self, tmp_path):
        a = archive(tmp_path, {"20260902T000000Z": R1, "20260905T000000Z": R1 + R2})
        r = sn.compare(write(tmp_path, "s.ndjson", R1 + R2 + R3), sn.snapshot_list(a))
        assert r["identical_to"] is None and r["extends"] == "ai-arz-serisi-20260905T000000Z.ndjson"
        assert r["added_runs"] == [{"zaman_utc": "2026-09-08T07:00:00+00:00", "rows": 2}]

    def test_reordered_copy_extends_no_snapshot(self, tmp_path):
        a = archive(tmp_path, {"20260902T000000Z": R1})
        lines = R1.splitlines(True)
        r = sn.compare(write(tmp_path, "s.ndjson", lines[1] + lines[0] + R2), sn.snapshot_list(a))
        assert r["identical_to"] is None and r["extends"] is None and r["added_runs"] is None

    def test_older_copy_extends_only_older_snapshots(self, tmp_path):
        a = archive(tmp_path, {"20260902T000000Z": R1, "20260905T000000Z": R1 + R2})
        r = sn.compare(write(tmp_path, "s.ndjson", R1), sn.snapshot_list(a))
        assert r["extends"] == r["identical_to"] == "ai-arz-serisi-20260902T000000Z.ndjson"


class TestMain:
    def test_text(self, tmp_path, capsys):
        a = archive(tmp_path, {"20260902T000000Z": R1})
        f = write(tmp_path, "s.ndjson", R1 + R2)
        assert sn.main(["--archive", str(a), "--file", str(f)]) == 0
        out = capsys.readouterr().out
        assert "proof matches, pending (1 pending, 0 bitcoin)" in out
        assert "identical to: no snapshot" in out and "extends: ai-arz-serisi-20260902T000000Z.ndjson" in out
        assert "2026-09-04T07:00:00+00:00  1 rows" in out

    def test_text_for_a_file_that_extends_nothing(self, tmp_path, capsys):
        a = archive(tmp_path, {"20260902T000000Z": R1})
        assert sn.main(["--archive", str(a), "--file", str(write(tmp_path, "s.ndjson", R2))]) == 0
        assert "extends: no snapshot" in capsys.readouterr().out

    def test_json(self, tmp_path, capsys):
        a = archive(tmp_path, {"20260902T000000Z": R1}, {"20260902T000000Z": proof(R1.encode(), 0, 2)})
        assert sn.main(["--archive", str(a), "--file", str(write(tmp_path, "s.ndjson", R1)), "--json"]) == 0
        r = json.loads(capsys.readouterr().out)
        assert r["snapshots"][0]["proof"]["bitcoin"] == 2 and r["file"]["identical_to"].endswith("T000000Z.ndjson")

    def test_missing_file_exits_with_an_error(self, tmp_path, capsys):
        a = archive(tmp_path, {"20260902T000000Z": R1})
        assert sn.main(["--archive", str(a), "--file", str(tmp_path / "yok")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            sn.main(["--help"])
        assert "extends byte for byte" in " ".join(capsys.readouterr().out.split())


def test_published_series_extends_the_newest_snapshot_and_every_proof_matches():
    pairs = sn.snapshot_list(KOK / "archive")
    assert pairs and all(e["proof"] is not None and e["proof"]["matches"] for e, _ in pairs)
    r = sn.compare(KOK / "ai-arz-serisi.ndjson", pairs)
    assert r["extends"] == pairs[-1][0]["snapshot"]
    assert r["rows"] == pairs[-1][0]["rows"] + sum(x["rows"] for x in r["added_runs"])
