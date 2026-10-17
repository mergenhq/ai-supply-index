"""Tests for examples/to_sqlite.py — a small fixture file under tmp_path; the published series is
read only up to 2026-10-05T23:59:59, so new weekly rows cannot change these tests."""
import importlib.util
import json
import sqlite3

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("to_sqlite", KOK / "examples" / "to_sqlite.py")
ts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ts)

CUTOFF = "2026-10-05T23:59:59"

FIXTURE = [
    # v0.1 row: no surum or saniye, with http, url and bayt
    {"zaman_utc": "2026-08-18T07:04:52+00:00", "uc": "x402_discovery", "url": "https://example.org/r",
     "not": "n1", "http": 200, "bayt": 64889, "ozet": {"kaynak_sayisi": 15095, "sayfa_ogesi": 20}, "durum": "OK"},
    # nested lists, an empty list, a null, a boolean, floats
    {"zaman_utc": "2026-09-28T07:00:01+00:00", "surum": "0.3", "uc": "sherlock_contests", "not": "n2",
     "ozet": {"yarisma_sayisi": 301, "acik_yarisma": None, "acik_kapilar": [],
              "dag": {"n": 2, "p50": 1.5, "histogram": {"<1": 0, ">=10": 1}},
              "liste": [{"kamu": True, "baslik": "a"}, {"kamu": False, "baslik": "b"}]},
     "durum": "OK", "saniye": 2.5},
    # package names with "/" and "~", an error row inside a package
    {"zaman_utc": "2026-09-28T07:00:01+00:00", "surum": "0.3", "uc": "npm_downloads", "not": "n3",
     "ozet": {"@anthropic-ai/sdk": {"toplam_30g": 5}, "a~b": {"hata": "429"}, "bos": {}},
     "durum": "OK", "saniye": 3, "toplayici": "c1"},
    # failed row without a summary, and a key outside the envelope
    {"zaman_utc": "2026-09-28T07:00:01+00:00", "surum": "0.3", "uc": "apify_store", "not": "n4",
     "durum": "HATA", "hata": "TimeoutError()", "saniye": 30.0, "yeni_alan": [1, 2]},
]
# leaves per fixture row: 2; 1 + 1 + 1 (empty list) + 4 (dag) + 4 (liste) = 11; 3; 0
LEAVES = 2 + 11 + 3 + 0


def build(tmp_path, rows=FIXTURE, raw=()):
    src = tmp_path / "s.ndjson"
    src.write_text("".join(json.dumps(r) + "\n" for r in rows) + "".join(x + "\n" for x in raw), encoding="utf-8")
    db = tmp_path / "s.sqlite"
    assert ts.main(["--series", str(src), "--db", str(db)]) == 0
    return sqlite3.connect(db)


def one(db, sql, *args):
    return db.execute(sql, args).fetchone()


class TestCounts:
    def test_row_and_leaf_counts(self, tmp_path, capsys):
        db = build(tmp_path)
        assert one(db, "SELECT count(*) FROM rows") == (4,)
        assert one(db, "SELECT count(*) FROM leaves") == (LEAVES,)
        assert "(4 rows, %d leaves)" % LEAVES in capsys.readouterr().out

    def test_leaves_per_row(self, tmp_path):
        db = build(tmp_path)
        assert db.execute("SELECT row_id, count(*) FROM leaves GROUP BY row_id ORDER BY row_id").fetchall() == [
            (1, 2), (2, 11), (3, 3)]

    def test_blank_lines_are_skipped_and_row_id_is_the_line_number(self, tmp_path):
        src = tmp_path / "s.ndjson"
        src.write_text(json.dumps(FIXTURE[0]) + "\n\n" + json.dumps(FIXTURE[1]) + "\n", encoding="utf-8")
        assert ts.main(["--series", str(src), "--db", str(tmp_path / "d.sqlite")]) == 0
        db = sqlite3.connect(tmp_path / "d.sqlite")
        assert [r[0] for r in db.execute("SELECT row_id FROM rows")] == [1, 3]


class TestRows:
    def test_envelope_columns_follow_the_schema_map(self, tmp_path):
        db = build(tmp_path)
        cols = [c[1] for c in db.execute("PRAGMA table_info(rows)")]
        m = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))
        env = [k[0] for g in m["groups"] if g["name"] == "Record envelope" for k in g["keys"] if k[0] != "ozet"]
        assert cols == ["row_id"] + env + ["has_ozet", "extra"]

    def test_missing_envelope_values_are_null_not_zero(self, tmp_path):
        db = build(tmp_path)
        assert one(db, 'SELECT surum, saniye, http, bayt, hata, toplayici FROM rows WHERE row_id = 1') == (
            None, None, 200, 64889, None, None)
        assert one(db, 'SELECT http, bayt, url FROM rows WHERE row_id = 2') == (None, None, None)

    def test_values_and_types(self, tmp_path):
        db = build(tmp_path)
        assert one(db, 'SELECT zaman_utc, uc, "not", durum, saniye, typeof(saniye) FROM rows WHERE row_id = 2') == (
            "2026-09-28T07:00:01+00:00", "sherlock_contests", "n2", "OK", 2.5, "real")
        assert one(db, "SELECT toplayici, has_ozet FROM rows WHERE row_id = 3") == ("c1", 1)

    def test_failed_row_without_summary(self, tmp_path):
        db = build(tmp_path)
        assert one(db, "SELECT durum, hata, has_ozet, extra FROM rows WHERE row_id = 4") == (
            "HATA", "TimeoutError()", 0, '{"yeni_alan": [1, 2]}')
        assert one(db, "SELECT count(*) FROM leaves WHERE row_id = 4") == (0,)


class TestLeaves:
    def leaf(self, db, row_id, path):
        return one(db, "SELECT value, type FROM leaves WHERE row_id = ? AND path = ?", row_id, path)

    def test_scalars(self, tmp_path):
        db = build(tmp_path)
        assert self.leaf(db, 1, "/kaynak_sayisi") == (15095, "integer")
        assert self.leaf(db, 2, "/dag/p50") == (1.5, "real")
        assert self.leaf(db, 2, "/liste/1/baslik") == ("b", "text")

    def test_null_stays_null(self, tmp_path):
        db = build(tmp_path)
        assert self.leaf(db, 2, "/acik_yarisma") == (None, "null")

    def test_empty_containers_are_null_with_their_type(self, tmp_path):
        db = build(tmp_path)
        assert self.leaf(db, 2, "/acik_kapilar") == (None, "empty_array")
        assert self.leaf(db, 3, "/bos") == (None, "empty_object")

    def test_booleans(self, tmp_path):
        db = build(tmp_path)
        assert self.leaf(db, 2, "/liste/0/kamu") == (1, "boolean")
        assert self.leaf(db, 2, "/liste/1/kamu") == (0, "boolean")

    def test_measured_zero_is_kept(self, tmp_path):
        db = build(tmp_path)
        assert self.leaf(db, 2, "/dag/histogram/<1") == (0, "integer")

    def test_keys_with_slash_and_tilde_are_escaped(self, tmp_path):
        db = build(tmp_path)
        assert self.leaf(db, 3, "/@anthropic-ai~1sdk/toplam_30g") == (5, "integer")
        assert self.leaf(db, 3, "/a~0b/hata") == ("429", "text")

    def test_pointer(self):
        assert ts.pointer(["a/b", 0, "c~d"]) == "/a~1b/0/c~0d" and ts.pointer([]) == ""


class TestMain:
    def test_existing_database_needs_replace(self, tmp_path, capsys):
        build(tmp_path)
        src, db = tmp_path / "s.ndjson", tmp_path / "s.sqlite"
        assert ts.main(["--series", str(src), "--db", str(db)]) == 1
        assert "--replace" in capsys.readouterr().err
        assert ts.main(["--series", str(src), "--db", str(db), "--replace"]) == 0
        assert one(sqlite3.connect(db), "SELECT count(*) FROM rows") == (4,)

    @pytest.mark.parametrize("bad, msg", [("{bozuk", "line 2 is not valid JSON"), ("42", "line 2 is not a JSON object")])
    def test_bad_line_leaves_no_database(self, tmp_path, capsys, bad, msg):
        src = tmp_path / "s.ndjson"
        src.write_text(json.dumps(FIXTURE[0]) + "\n" + bad + "\n", encoding="utf-8")
        assert ts.main(["--series", str(src), "--db", str(tmp_path / "x.sqlite")]) == 1
        assert msg in capsys.readouterr().err and not (tmp_path / "x.sqlite").exists()

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            ts.main(["--help"])
        assert "Missing values are NULL, never 0" in " ".join(capsys.readouterr().out.split())


def test_published_rows_up_to_the_cutoff(tmp_path, capsys):
    lines = [x for x in (KOK / "ai-arz-serisi.ndjson").read_text(encoding="utf-8").splitlines()
             if x.strip() and json.loads(x)["zaman_utc"] <= CUTOFF]
    rows = [json.loads(x) for x in lines]
    db = build(tmp_path, rows)
    assert one(db, "SELECT count(*) FROM rows") == (len(rows),)
    assert one(db, "SELECT count(*) FROM leaves") == (sum(len(list(ts.leaves(r["ozet"]))) for r in rows if "ozet" in r),)
    assert one(db, "SELECT count(*) FROM rows WHERE has_ozet = 0") == (sum(1 for r in rows if "ozet" not in r),)
    got = one(db, "SELECT l.value FROM rows r JOIN leaves l USING (row_id) WHERE r.zaman_utc = "
                  "'2026-09-28T07:00:01+00:00' AND r.uc = 'x402_discovery' AND l.path = '/kaynak_sayisi'")
    assert got == (17820,)
