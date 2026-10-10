"""Tests for examples/codebook.py — the real schema_map.json is only read; other maps live under tmp_path."""
import csv
import importlib.util
import io
import json

import pytest

import to_english as te
from conftest import KOK

_spec = importlib.util.spec_from_file_location("codebook", KOK / "examples" / "codebook.py")
cb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cb)

MAP = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))


def run_csv(capsys, *args):
    assert cb.main(list(args)) == 0
    return list(csv.DictReader(io.StringIO(capsys.readouterr().out)))


class TestRealMap:
    def test_header(self, capsys):
        assert cb.main([]) == 0
        assert capsys.readouterr().out.splitlines()[0] == ",".join(cb.COLUMNS)

    def test_one_key_row_per_mapped_key_in_file_order(self, capsys):
        rows = [r for r in run_csv(capsys) if r["section"] == "key"]
        want = [(g["name"], k[0], k[1], k[2], k[3]) for g in MAP["groups"] for k in g["keys"]]
        assert [(r["group"], r["key"], r["english_key"], r["type"], r["description"]) for r in rows] == want

    def test_key_rows_match_what_to_english_loads(self, capsys):
        _, keys = te.harita_yukle()
        rows = [r for r in run_csv(capsys) if r["section"] == "key"]
        assert {r["key"]: r["english_key"] for r in rows} == keys
        assert len(rows) == MAP["_meta"]["key_count"]

    def test_passthrough_rows_come_first_and_are_marked(self, capsys):
        rows = run_csv(capsys)
        assert [r["section"] for r in rows[:2]] == ["passthrough", "passthrough"]
        assert [r["group"] for r in rows[:2]] == list(MAP["passthrough"])
        assert all(r["section"] == "key" for r in rows[2:])

    def test_passthrough_description_lists_endpoints_and_examples(self, capsys):
        pkg = next(r for r in run_csv(capsys) if r["group"] == "package_identifiers")
        for name in MAP["passthrough"]["package_identifiers"]["endpoints"]:
            assert name in pkg["description"]
        assert "@anthropic-ai/sdk" in pkg["description"]

    def test_descriptions_keep_pipes_unescaped(self, capsys):
        durum = next(r for r in run_csv(capsys) if r["key"] == "durum")
        assert durum["description"].startswith("OK | HATA") and "\\|" not in durum["description"]

    def test_every_row_has_every_column(self, capsys):
        assert all(all(r[c] for c in cb.COLUMNS) for r in run_csv(capsys))


class TestOtherMaps:
    def write(self, tmp_path, m):
        p = tmp_path / "map.json"
        p.write_text(json.dumps(m), encoding="utf-8")
        return p

    def test_small_map_and_comma_in_description(self, tmp_path, capsys):
        p = self.write(tmp_path, {"groups": [{"name": "G", "note": "n", "keys": [
            ["a", "alpha", "string", "first, with a comma"], ["b", "beta", "integer", 'has "quotes"']]}]})
        rows = run_csv(capsys, "--schema-map", str(p))
        assert [(r["key"], r["english_key"], r["description"]) for r in rows] == [
            ("a", "alpha", "first, with a comma"), ("b", "beta", 'has "quotes"')]

    def test_map_without_passthrough(self, tmp_path):
        rows = cb.codebook({"groups": [{"name": "G", "keys": [["a", "alpha", "string", "d"]]}]})
        assert [r["section"] for r in rows] == ["key"]

    def test_out_file(self, tmp_path, capsys):
        out = tmp_path / "codebook.csv"
        assert cb.main(["--out", str(out)]) == 0 and capsys.readouterr().out == ""
        assert len(list(csv.DictReader(out.open(encoding="utf-8")))) == MAP["_meta"]["key_count"] + 2

    @pytest.mark.parametrize("content", ["{bozuk", '{"passthrough": {}}'])
    def test_unreadable_map_exits_with_an_error(self, tmp_path, capsys, content):
        p = tmp_path / "map.json"
        p.write_text(content, encoding="utf-8")
        assert cb.main(["--schema-map", str(p)]) == 1 and "error:" in capsys.readouterr().err

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            cb.main(["--help"])
        assert "one row per key in file order" in " ".join(capsys.readouterr().out.split())
