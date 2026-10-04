"""Tests for examples/validate_series.py — small fixture files under tmp_path; the published files are only read."""
import importlib.util
import json

import pytest

from conftest import KOK

_spec = importlib.util.spec_from_file_location("validate_series", KOK / "examples" / "validate_series.py")
vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs)

RULES = vs.Rules()
GOOD = {"zaman_utc": "2026-09-28T07:00:01+00:00", "surum": "0.3", "uc": "x402_discovery",
        "not": "n", "ozet": {"kaynak_sayisi": 1}, "durum": "OK", "saniye": 1.5}


def fixture(tmp_path, rows, raw=()):
    p = tmp_path / "s.ndjson"
    lines = [json.dumps(r) for r in rows] + list(raw)
    p.write_text("".join(x + "\n" for x in lines), encoding="utf-8")
    return p


def checks(row):
    return [c for c, _ in vs.check_row(row, RULES)]


class TestRules:
    def test_envelope_keys_come_from_the_schema_map(self):
        m = json.loads((KOK / "schema_map.json").read_text(encoding="utf-8"))
        env = next(g for g in m["groups"] if g["name"] == "Record envelope")
        assert set(RULES.types) == {k[0] for k in env["keys"]}

    def test_durum_values_come_from_the_schema_map(self):
        assert RULES.durum == {"OK", "HATA", "HTTP-HATA", "HATA-ICERIDE"}

    def test_known_endpoint_matches_whole_names_only(self):
        assert RULES.known_endpoint("x402_discovery") and RULES.known_endpoint("github_repos")
        assert not RULES.known_endpoint("github") and not RULES.known_endpoint("x402_discovery_v2")


class TestCheckRow:
    def test_complete_row_passes(self):
        assert vs.check_row(GOOD, RULES) == []

    @pytest.mark.parametrize("extra", [{"http": 503}, {"hata": "TimeoutError()"},
                                       {"url": "https://x", "bayt": 10}, {"toplayici": "c1"}])
    def test_optional_envelope_keys_pass(self, extra):
        assert vs.check_row(dict(GOOD, **extra), RULES) == []

    def test_row_without_optional_keys_passes(self):
        assert vs.check_row({k: GOOD[k] for k in ("zaman_utc", "uc", "not", "durum")}, RULES) == []

    @pytest.mark.parametrize("key", ["zaman_utc", "uc", "not", "durum"])
    def test_missing_required_key_fails(self, key):
        row = dict(GOOD)
        del row[key]
        assert checks(row) == ["envelope"]

    def test_unknown_top_level_key_fails(self):
        assert checks(dict(GOOD, bilinmeyen=1)) == ["envelope"]

    @pytest.mark.parametrize("key, value", [("ozet", [1]), ("saniye", "1.5"), ("saniye", True),
                                            ("http", 503.0), ("not", None), ("uc", 7)])
    def test_wrong_type_fails(self, key, value):
        assert "envelope" in checks(dict(GOOD, **{key: value}))

    def test_integer_is_a_number(self):
        assert vs.check_row(dict(GOOD, saniye=2), RULES) == []

    @pytest.mark.parametrize("z", ["2026-09-28T07:00:01Z", "2026-09-28T09:00:01+02:00"])
    def test_iso_time_with_offset_passes(self, z):
        assert vs.check_row(dict(GOOD, zaman_utc=z), RULES) == []

    @pytest.mark.parametrize("z", ["2026-09-28T07:00:01", "28.09.2026 07:00", "", "2026-13-01T00:00:00+00:00"])
    def test_time_without_offset_or_unparseable_fails(self, z):
        assert checks(dict(GOOD, zaman_utc=z)) == ["zaman_utc"]

    def test_endpoint_not_in_schema_map_fails(self):
        assert checks(dict(GOOD, uc="bilinmeyen_uc")) == ["uc"]

    @pytest.mark.parametrize("d", ["ok", "ERROR", "HATA-ICINDE", ""])
    def test_unknown_durum_fails(self, d):
        assert checks(dict(GOOD, durum=d)) == ["durum"]

    @pytest.mark.parametrize("d", ["OK", "HATA", "HTTP-HATA", "HATA-ICERIDE"])
    def test_known_durum_passes(self, d):
        assert vs.check_row(dict(GOOD, durum=d), RULES) == []

    @pytest.mark.parametrize("row", [42, "x", [1], None])
    def test_non_object_fails(self, row):
        assert checks(row) == ["json"]

    def test_several_problems_are_all_reported(self):
        assert sorted(checks({"zaman_utc": "dun", "uc": "yok", "durum": "?", "x": 1})) == [
            "durum", "envelope", "envelope", "uc", "zaman_utc"]


class TestValidate:
    def test_counts_per_durum_and_endpoint(self, tmp_path):
        r = vs.validate(fixture(tmp_path, [GOOD, dict(GOOD, durum="HATA"), dict(GOOD, uc="github_repos")]), RULES)
        assert r["rows"] == 3 and r["rows_failing"] == 0
        assert r["per_durum"] == {"HATA": 1, "OK": 2}
        assert r["per_endpoint"] == {"github_repos": 1, "x402_discovery": 2}

    def test_problems_name_the_line(self, tmp_path):
        r = vs.validate(fixture(tmp_path, [GOOD, dict(GOOD, durum="X")], raw=["", "{bozuk"]), RULES)
        assert r["rows"] == 3 and r["rows_failing"] == 2
        assert [(p["line"], p["check"]) for p in r["problems"]] == [(2, "durum"), (4, "json")]
        assert r["problems_per_check"] == {"durum": 1, "json": 1}

    def test_blank_lines_are_not_rows(self, tmp_path):
        assert vs.validate(fixture(tmp_path, [GOOD], raw=["", "  "]), RULES)["rows"] == 1


class TestMain:
    def test_passing_file_exits_0(self, tmp_path, capsys):
        assert vs.main(["--series", str(fixture(tmp_path, [GOOD]))]) == 0
        out = capsys.readouterr().out
        assert "OK: every row passes" in out and "x402_discovery" in out

    def test_failing_file_exits_1_and_lists_problems(self, tmp_path, capsys):
        p = fixture(tmp_path, [GOOD, dict(GOOD, zaman_utc="dun")])
        assert vs.main(["--series", str(p)]) == 1
        out = capsys.readouterr().out
        assert "FAIL: 1 of 2 rows fail a check (zaman_utc=1)" in out and "line 2: [zaman_utc]" in out

    def test_problem_list_is_limited(self, tmp_path, capsys):
        p = fixture(tmp_path, [dict(GOOD, durum="X")] * 5)
        assert vs.main(["--series", str(p), "--max-problems", "2"]) == 1
        out = capsys.readouterr().out
        assert out.count("[durum]") == 2 and "... 3 more" in out

    def test_json_report(self, tmp_path, capsys):
        assert vs.main(["--series", str(fixture(tmp_path, [GOOD])), "--json"]) == 0
        r = json.loads(capsys.readouterr().out)
        assert r["rows"] == 1 and r["problems"] == [] and r["per_durum"] == {"OK": 1}

    def test_missing_file_exits_2(self, tmp_path, capsys):
        assert vs.main(["--series", str(tmp_path / "yok.ndjson")]) == 2
        assert "error:" in capsys.readouterr().err

    def test_unreadable_schema_map_exits_2(self, tmp_path, capsys):
        bad = tmp_path / "map.json"
        bad.write_text("{}", encoding="utf-8")
        assert vs.main(["--series", str(fixture(tmp_path, [GOOD])), "--schema-map", str(bad)]) == 2

    def test_help_text_is_in_english(self, capsys):
        with pytest.raises(SystemExit):
            vs.main(["--help"])
        assert "1 = at least one row fails a check" in " ".join(capsys.readouterr().out.split())


def test_published_series_passes_the_envelope_time_and_durum_checks():
    r = vs.validate(KOK / "ai-arz-serisi.ndjson", RULES)
    assert r["rows"] > 0
    assert [p for p in r["problems"] if p["check"] != "uc"] == []
