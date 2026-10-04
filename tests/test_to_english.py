"""Tests for to_english.py — synthetic maps/series under tmp_path; the real schema_map.json
and series are only READ."""
import json

import pytest

import to_english as te
from conftest import KOK

META = {"passthrough": {"package_identifiers": {"endpoints": ["npm_downloads"]}}}
KEYS = {"zaman_utc": "time_utc", "uc": "endpoint", "ozet": "summary", "kaynak_sayisi": "resource_count",
        "taranan": "scanned", "toplam_30g": "downloads_30d", "cagri_30g": "calls_30d", "n": "n"}


def harita_dosyasi(tmp_path, gruplar, key_count=None):
    m = {"_meta": {"key_count": key_count}, "passthrough": {}, "groups": gruplar}
    p = tmp_path / "map.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def ndjson(tmp_path, nesneler, ad="seri.ndjson", ham=None):
    p = tmp_path / ad
    satirlar = [json.dumps(o, ensure_ascii=False) for o in nesneler] + (ham or [])
    p.write_text("".join(s + "\n" for s in satirlar), encoding="utf-8")
    return p


# ── harita_yukle ────────────────────────────────────────────────────────────
class TestHaritaYukle:
    def test_flattens_groups(self, tmp_path):
        p = harita_dosyasi(tmp_path, [{"name": "a", "keys": [["x", "ex", "int", "d"]]},
                                      {"name": "b", "keys": [["y", "why", "int", "d"]]}])
        m, keys = te.harita_yukle(p)
        assert keys == {"x": "ex", "y": "why"} and m["groups"][1]["name"] == "b"

    def test_empty_groups(self, tmp_path):
        assert te.harita_yukle(harita_dosyasi(tmp_path, []))[1] == {}

    def test_duplicate_turkish_key_rejected(self, tmp_path):
        p = harita_dosyasi(tmp_path, [{"name": "a", "keys": [["x", "ex"]]},
                                      {"name": "b", "keys": [["x", "ex2"]]}])
        with pytest.raises(ValueError, match="duplicate Turkish key.*'a'.*'b'"):
            te.harita_yukle(p)

    @pytest.mark.parametrize("en", ["", None, 5])
    def test_empty_or_non_string_target_rejected(self, tmp_path, en):
        p = harita_dosyasi(tmp_path, [{"name": "a", "keys": [["x", en]]}])
        with pytest.raises(ValueError, match="empty English name"):
            te.harita_yukle(p)

    def test_missing_groups_field(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text("{}", encoding="utf-8")
        with pytest.raises(KeyError):
            te.harita_yukle(p)

    def test_corrupt_map_file(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text("{bozuk", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            te.harita_yukle(p)

    def test_real_map_is_consistent(self):
        meta, keys = te.harita_yukle()
        assert meta["_meta"]["key_count"] == len(keys)
        assert all(not any(ch in v for ch in "çğıöşüÇĞİÖŞÜ ") for v in keys.values())
        assert keys["olculemedi"] == "unmeasurable"


# ── cevir ───────────────────────────────────────────────────────────────────
class TestCevir:
    def test_maps_nested_keys(self):
        eks = []
        out = te.cevir({"uc": "x", "ozet": {"kaynak_sayisi": 3}}, "x", [], KEYS, META, eks)
        assert out == {"endpoint": "x", "summary": {"resource_count": 3}} and eks == []

    def test_lists_are_walked(self):
        out = te.cevir({"ozet": [{"taranan": 1}, 2, [{"n": 3}]]}, "x", [], KEYS, META, [])
        assert out == {"summary": [{"scanned": 1}, 2, [{"n": 3}]]}

    @pytest.mark.parametrize("deger", [None, 0, 1.5, "s", True, [], {}])
    def test_scalars_and_empties_unchanged(self, deger):
        assert te.cevir(deger, "x", [], KEYS, META, []) == deger

    def test_values_are_never_translated(self):
        assert te.cevir({"uc": "ozet"}, "x", [], KEYS, META, []) == {"endpoint": "ozet"}

    def test_unknown_key_reported_with_path_and_kept(self):
        eks = []
        out = te.cevir({"ozet": {"a": {"bilinmeyen": 1}}}, "x402", [], KEYS, META, eks)
        assert eks == [{"key": "a", "endpoint": "x402", "path": "ozet"},
                       {"key": "bilinmeyen", "endpoint": "x402", "path": "ozet/a"}]
        assert out == {"summary": {"a": {"bilinmeyen": 1}}}

    def test_unknown_root_key_path(self):
        eks = []
        te.cevir({"yeni": 1}, "x", [], KEYS, META, eks)
        assert eks[0]["path"] == "<root>"

    def test_collision_raises(self):
        k = dict(KEYS, taranan="resource_count")
        with pytest.raises(te.AdCakismasi, match="kaynak_sayisi.*taranan.*resource_count"):
            te.cevir({"kaynak_sayisi": 1, "taranan": 2}, "x", ["ozet"], k, META, [])

    def test_collision_between_passthrough_and_mapped_key(self):
        # unknown key "summary" kept verbatim collides with "ozet" -> "summary"
        with pytest.raises(te.AdCakismasi):
            te.cevir({"ozet": 1, "summary": 2}, "x", [], KEYS, META, [])

    def test_histogram_children_pass_through_but_values_recurse(self):
        h = {"histogram": {"<1": 1, "1-10": {"n": 2}, "ozet": 3}}
        eks = []
        out = te.cevir(h, "x", ["ozet", "cagri_30g"], KEYS, META, eks)
        assert eks == [{"key": "histogram", "endpoint": "x", "path": "ozet/cagri_30g"}]
        assert out["histogram"] == {"<1": 1, "1-10": {"n": 2}, "ozet": 3}

    def test_package_ids_only_directly_under_ozet_for_listed_endpoints(self):
        out = te.cevir({"@anthropic-ai/sdk": {"toplam_30g": 5}}, "npm_downloads", ["ozet"], KEYS, META, [])
        assert out == {"@anthropic-ai/sdk": {"downloads_30d": 5}}
        eks = []
        te.cevir({"@anthropic-ai/sdk": {}}, "hf_models", ["ozet"], KEYS, META, eks)
        assert [e["key"] for e in eks] == ["@anthropic-ai/sdk"]
        eks = []
        te.cevir({"@anthropic-ai/sdk": {}}, "npm_downloads", ["ozet", "x"], KEYS, META, eks)
        assert len(eks) == 1

    def test_veri_anahtari(self):
        assert te._veri_anahtari("<1", "x", ["a", "histogram"], META)
        assert not te._veri_anahtari("<1", "x", [], META)
        assert te._veri_anahtari("pkg", "npm_downloads", ["ozet"], META)
        assert not te._veri_anahtari("pkg", "npm_downloads", [], META)


# ── seriyi_cevir / ingilizce_yaz ────────────────────────────────────────────
class TestSeri:
    def test_converts_rows_and_skips_blank_lines(self, tmp_path):
        p = ndjson(tmp_path, [{"uc": "a", "taranan": 1}], ham=["", "   ", json.dumps({"uc": "b"})])
        rows, eks = te.seriyi_cevir(p, KEYS, META)
        assert rows == [{"endpoint": "a", "scanned": 1}, {"endpoint": "b"}] and eks == []

    def test_empty_file(self, tmp_path):
        p = tmp_path / "s.ndjson"
        p.write_text("", encoding="utf-8")
        assert te.seriyi_cevir(p, KEYS, META) == ([], [])

    def test_row_without_uc_uses_placeholder_endpoint(self, tmp_path):
        rows, eks = te.seriyi_cevir(ndjson(tmp_path, [{"x": 1}]), KEYS, META)
        assert eks == [{"key": "x", "endpoint": "?", "path": "<root>"}]

    def test_duplicate_rows_are_preserved(self, tmp_path):
        r = {"uc": "a", "taranan": 1}
        rows, _ = te.seriyi_cevir(ndjson(tmp_path, [r, r]), KEYS, META)
        assert rows == [{"endpoint": "a", "scanned": 1}] * 2

    def test_corrupt_line_fails_loudly(self, tmp_path):
        p = ndjson(tmp_path, [{"uc": "a"}], ham=["{bozuk"])
        with pytest.raises(json.JSONDecodeError):
            te.seriyi_cevir(p, KEYS, META)

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            te.seriyi_cevir(tmp_path / "yok", KEYS, META)

    def test_write_mirror(self, tmp_path, capsys):
        cikti = tmp_path / "en.ndjson"
        p = ndjson(tmp_path, [{"uc": "a", "ozet": {"kaynak_sayisi": "ç"}}])
        assert te.ingilizce_yaz(p, cikti, KEYS, META) == 0
        assert cikti.read_text(encoding="utf-8") == '{"endpoint": "a", "summary": {"resource_count": "ç"}}\n'
        assert "1 rows" in capsys.readouterr().out

    def test_write_overwrites_previous_mirror(self, tmp_path, capsys):
        cikti = tmp_path / "en.ndjson"
        cikti.write_text("eski\n", encoding="utf-8")
        te.ingilizce_yaz(ndjson(tmp_path, [{"uc": "a"}]), cikti, KEYS, META)
        assert cikti.read_text(encoding="utf-8") == '{"endpoint": "a"}\n'

    def test_unknown_key_refuses_to_write(self, tmp_path, capsys):
        cikti = tmp_path / "en.ndjson"
        p = ndjson(tmp_path, [{"uc": "a", "yeni": 1}, {"uc": "a", "yeni": 2}])
        with pytest.raises(te.SemaBoslugu, match="1 unmapped"):    # de-duplicated
            te.ingilizce_yaz(p, cikti, KEYS, META)
        assert not cikti.exists()
        assert "key=yeni" in capsys.readouterr().err

    def test_real_series_has_no_schema_gap(self):
        meta, keys = te.harita_yukle()
        rows, eks = te.seriyi_cevir(KOK / "ai-arz-serisi.ndjson", keys, meta)
        assert rows and eks == []

    def test_conversion_preserves_every_leaf(self, tmp_path):
        meta, keys = te.harita_yukle()
        p = KOK / "ai-arz-serisi.ndjson"
        ham = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        rows, _ = te.seriyi_cevir(p, keys, meta)
        assert len(rows) == len(ham)
        assert sorted(map(repr, te._yapraklar(ham, []))) == sorted(map(repr, te._yapraklar(rows, [])))


def test_yapraklar():
    assert te._yapraklar({"a": [1, {"b": None}], "c": "x"}, []) == [1, None, "x"]
    assert te._yapraklar({}, []) == []


# ── Markdown ────────────────────────────────────────────────────────────────
class TestSemaMd:
    def test_hucre_escapes_pipe(self):
        assert te._hucre("a|b") == "a\\|b" and te._hucre(3) == "3"

    def test_every_key_appears_once_and_rows_have_four_columns(self):
        _, keys = te.harita_yukle()
        md = te.sema_md()
        satirlar = md.splitlines()
        for tr in keys:
            assert sum(ln.startswith("| `%s` |" % tr) for ln in satirlar) == 1, tr
        for ln in md.splitlines():
            if ln.startswith("| `"):
                assert len(ln.replace("\\|", "").split("|")) - 1 == 5, ln


# ── CLI ─────────────────────────────────────────────────────────────────────
class TestMain:
    def calistir(self, monkeypatch, argv):
        monkeypatch.setattr("sys.argv", ["to_english.py"] + argv)
        return te.main()

    def test_english_writes_requested_out(self, tmp_path, monkeypatch, capsys):
        p = ndjson(tmp_path, [{"zaman_utc": "t", "uc": "x402_discovery", "ozet": {"kaynak_sayisi": 1}}])
        cikti = tmp_path / "en.ndjson"
        assert self.calistir(monkeypatch, ["--english", "--series", str(p), "--out", str(cikti)]) == 0
        assert json.loads(cikti.read_text(encoding="utf-8")) == {
            "timestamp_utc": "t", "endpoint": "x402_discovery", "summary": {"resource_count": 1}}

    def test_english_schema_gap_exit_1(self, tmp_path, monkeypatch, capsys):
        p = ndjson(tmp_path, [{"uc": "x", "bilinmeyen_alan": 1}])
        cikti = tmp_path / "en.ndjson"
        assert self.calistir(monkeypatch, ["--english", "--series", str(p), "--out", str(cikti)]) == 1
        assert not cikti.exists()

    def test_schema_md(self, monkeypatch, capsys):
        assert self.calistir(monkeypatch, ["--schema-md"]) == 0
        assert "| key (as published) | English |" in capsys.readouterr().out

    def test_no_flag_prints_help(self, monkeypatch, capsys):
        assert self.calistir(monkeypatch, []) == 0
        assert "usage:" in capsys.readouterr().out

    def test_self_test_passes(self, tmp_path, monkeypatch, capsys):
        import tempfile
        monkeypatch.setattr(tempfile, "mkdtemp", lambda **k: str(tmp_path))
        assert self.calistir(monkeypatch, ["--self-test"]) == 0
        assert "16 passed / 0 failed" in capsys.readouterr().out


def test_open_window_summary_keys_are_all_mapped():
    """Every key an open-window summary can carry, including a full open entry, is in the map."""
    meta, keys = te.harita_yukle()
    ozet = {"yarisma_sayisi": 1, "sayfa_ogesi": 1, "sayfa": 1, "sayfa_alani": 1, "son_sayfa_alani": 1,
            "en_yeni_baslangic_utc": "2026-08-01T00:00:00+00:00",
            "acik_yarisma": 1, "acik_kamu": 1, "olculemedi": "x",
            "acik_kapilar": [{"arena": "cantina", "id": "a", "baslik": "t", "kamu": True,
                              "biter_utc": "2026-09-01T00:00:00+00:00", "kalan_gun": 1.5,
                              "odul": 10, "url": "https://example.org", "etiket": "e", "kyc": False}]}
    eksik = []
    te.cevir({"zaman_utc": "t", "uc": "sherlock_contests", "ozet": ozet}, "sherlock_contests",
             [], keys, meta, eksik)
    assert eksik == []


def test_envelope_keys_written_by_the_collector_are_mapped():
    _, keys = te.harita_yukle()
    for k in ("zaman_utc", "surum", "uc", "not", "ozet", "durum", "saniye", "http", "hata", "toplayici"):
        assert k in keys, k


def test_self_test_converts_a_full_open_entry(tmp_path, monkeypatch, capsys):
    import tempfile
    monkeypatch.setattr(tempfile, "mkdtemp", lambda **k: str(tmp_path))
    assert te.oz_test(KOK / "ai-arz-serisi.ndjson") == 0
    assert "open-window entry with every field converts with 0 unmapped keys" in capsys.readouterr().out


# ── the self-test reports a missing guard as a failure ──────────────────────
class TestSelfTestReportsMissingGuards:
    @pytest.fixture
    def oz_test(self, tmp_path, monkeypatch, capsys):
        import tempfile
        monkeypatch.setattr(tempfile, "mkdtemp", lambda **k: str(tmp_path))

        def calistir():
            kod = te.oz_test(KOK / "ai-arz-serisi.ndjson")
            return kod, capsys.readouterr().out
        return calistir

    def test_unknown_key_that_does_not_stop_the_run_is_a_failure(self, oz_test, monkeypatch):
        monkeypatch.setattr(te, "ingilizce_yaz", lambda *a, **k: 0)
        kod, out = oz_test()
        assert kod == 1
        assert "[FAIL] unknown key makes the run FAIL  — no exception raised" in out

    def test_name_collision_that_does_not_stop_the_run_is_a_failure(self, oz_test, monkeypatch):
        gercek = te.cevir

        def cevir(*a, **k):
            try:
                return gercek(*a, **k)
            except te.AdCakismasi:
                return {}
        monkeypatch.setattr(te, "cevir", cevir)
        kod, out = oz_test()
        assert kod == 1
        assert "[FAIL] name collision makes the run FAIL  — no exception raised" in out

    def test_malformed_table_row_is_a_failure(self, oz_test, monkeypatch):
        gercek = te.sema_md
        monkeypatch.setattr(te, "sema_md", lambda: gercek() + "\n| `x` | `y` | int |\n")
        kod, out = oz_test()
        assert kod == 1
        assert "[FAIL] every generated table row has exactly 4 columns  — 1 malformed" in out

    def test_clean_run_reports_no_failure(self, oz_test):
        kod, out = oz_test()
        assert kod == 0 and "[FAIL]" not in out


def test_script_entry_point_prints_help(monkeypatch, capsys):
    import runpy
    monkeypatch.setattr("sys.argv", ["to_english.py", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(te.__file__, run_name="__main__")
    assert e.value.code == 0
    assert capsys.readouterr().out.startswith("usage: to_english.py")
