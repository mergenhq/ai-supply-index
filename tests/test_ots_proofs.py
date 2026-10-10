"""Every published OpenTimestamps proof (archive/*.ots and the root ai-arz-serisi.ndjson.ots) parses
completely: header, version, a sha256 file digest, and a tree of operations whose every branch ends in
an attestation (a pending calendar URL or a Bitcoin block height). Files are only read; nothing is
sent to a calendar server."""
import pytest

from conftest import KOK

BASLIK = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OP_SHA256 = 0x08
BEKLEYEN = bytes.fromhex("83dfe30d2ef90c8e")
BITCOIN = bytes.fromhex("0588960d73d71901")
ARGUMANLI = {0xF0, 0xF1}                         # append, prepend
ARGUMANSIZ = {0x08, 0x02, 0x03, 0x67, 0xF2, 0xF3}  # sha256, sha1, ripemd160, keccak256, reverse, hexlify
KANITLAR = sorted((KOK / "archive").glob("*.ots")) + [KOK / "ai-arz-serisi.ndjson.ots"]


def varuint(b, i):
    deger = kaydir = 0
    while True:
        x = b[i]
        i += 1
        deger |= (x & 0x7F) << kaydir
        kaydir += 7
        if not x & 0x80:
            return deger, i


def varbytes(b, i):
    n, i = varuint(b, i)
    assert i + n <= len(b), "length runs past the end of the file"
    return b[i:i + n], i + n


def agac(b, i, onaylar):
    """Parse one timestamp tree from offset i; append (tag, payload) for each attestation."""
    while True:
        op = b[i]
        i += 1
        if op == 0xFF:                            # fork: a full subtree, then the rest
            i = agac(b, i, onaylar)
        elif op == 0x00:
            etiket = b[i:i + 8]
            yuk, i = varbytes(b, i + 8)
            onaylar.append((etiket, yuk))
            return i
        elif op in ARGUMANLI:
            arg, i = varbytes(b, i)
            assert arg, "empty argument"
        else:
            assert op in ARGUMANSIZ, "unknown operation 0x%02x at byte %d" % (op, i - 1)


def coz(yol):
    b = yol.read_bytes()
    assert b.startswith(BASLIK)
    i = len(BASLIK)
    assert b[i] == 1, "major version"
    assert b[i + 1] == OP_SHA256, "file digest operation"
    i += 2 + 32
    onaylar = []
    i = agac(b, i, onaylar)
    assert i == len(b), "%d bytes after the timestamp tree" % (len(b) - i)
    return onaylar


def test_there_is_a_proof_for_every_snapshot_and_the_root_file():
    assert len(KANITLAR) == len(list((KOK / "archive").glob("*.ndjson"))) + 1


@pytest.mark.parametrize("yol", KANITLAR, ids=lambda p: p.name)
def test_proof_parses_completely_and_every_branch_ends_in_an_attestation(yol):
    onaylar = coz(yol)
    assert onaylar
    for etiket, yuk in onaylar:
        if etiket == BEKLEYEN:
            url, son = varbytes(yuk, 0)
            assert son == len(yuk)
            assert url.startswith(b"https://") and b" " not in url, url
        else:
            assert etiket == BITCOIN, "unknown attestation %s" % etiket.hex()
            yukseklik, son = varuint(yuk, 0)
            assert son == len(yuk) and yukseklik > 0


@pytest.mark.parametrize("yol", KANITLAR, ids=lambda p: p.name)
def test_proof_reaches_more_than_one_calendar(yol):
    takvimler = {varbytes(y, 0)[0] for e, y in coz(yol) if e == BEKLEYEN}
    assert len(takvimler) >= 2 or any(e == BITCOIN for e, _ in coz(yol))


def test_parser_rejects_a_truncated_proof(tmp_path):
    kisa = tmp_path / "kisa.ots"
    kisa.write_bytes(KANITLAR[0].read_bytes()[:-5])
    with pytest.raises((AssertionError, IndexError)):
        coz(kisa)
