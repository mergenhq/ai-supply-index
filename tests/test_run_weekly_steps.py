"""Step-by-step checks on run_weekly.sh. The script runs in a temporary copy of the repository
layout with a stand-in collector and watchdog, and a stand-in `otsclient` module placed first on
PYTHONPATH, so nothing is collected, stamped against a calendar or sent over the network."""
import json
import os
import re
import shutil
import subprocess

import pytest

from conftest import KOK

DAMGA = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ ")


def kur(tmp_path, rc_toplayici=0, rc_bekci=0, rc_ots=0, satir='{"a": 1}', arsiv=()):
    kok = tmp_path / "repo"
    (kok / "archive").mkdir(parents=True)
    shutil.copy(KOK / "run_weekly.sh", kok / "run_weekly.sh")
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    (kok / "collector.py").write_text(
        "import json, os, sys\n"
        "json.dump({'cwd': os.getcwd(), 'argv': sys.argv[1:]}, open(%r, 'w'))\n"
        "if %r:\n    open('ai-arz-serisi.ndjson', 'a').write(%r + '\\n')\n"
        "sys.exit(%d)\n" % (str(kayit / "toplayici.json"), bool(satir), satir or "", rc_toplayici))
    (kok / "freshness_watchdog.py").write_text(
        "import json, sys\njson.dump(sys.argv[1:], open(%r, 'w'))\nsys.exit(%d)\n"
        % (str(kayit / "bekci.json"), rc_bekci))
    ots = tmp_path / "ots" / "otsclient"
    ots.mkdir(parents=True)
    (ots / "__init__.py").write_text("")
    (ots / "ots.py").write_text(
        "import json, sys\n"
        "def main():\n"
        "    json.dump(sys.argv, open(%r, 'w'))\n"
        "    open(sys.argv[-1] + '.ots', 'wb').write(b'proof')\n"
        "    sys.exit(%d)\n" % (str(kayit / "ots.json"), rc_ots))
    for ad, icerik in arsiv:
        (kok / "archive" / ad).write_text(icerik, encoding="utf-8")
    return kok, kayit


def calistir(tmp_path, kok, cwd=None, **ek):
    ortam = dict(os.environ, HOME=str(tmp_path / "home"),
                 PYTHONPATH=str(tmp_path / "ots") + os.pathsep + os.environ.get("PYTHONPATH", ""), **ek)
    return subprocess.run(["bash", str(kok / "run_weekly.sh")], cwd=cwd or tmp_path, env=ortam,
                          capture_output=True, text=True, timeout=60)


def oku(kayit, ad):
    p = kayit / ad
    return json.loads(p.read_text()) if p.exists() else None


def yeni_snapshotlar(kok, once=()):
    return sorted(p.name for p in (kok / "archive").glob("ai-arz-serisi-*.ndjson") if p.name not in once)


# ── step 1: collect ─────────────────────────────────────────────────────────
def test_collector_runs_in_the_repository_folder_without_arguments(tmp_path):
    kok, kayit = kur(tmp_path)
    calistir(tmp_path, kok, cwd=tmp_path)
    t = oku(kayit, "toplayici.json")
    assert t == {"cwd": str(kok), "argv": []}


# ── step 2: stamp a frozen copy ─────────────────────────────────────────────
def test_snapshot_is_a_dated_copy_of_the_series(tmp_path):
    kok, kayit = kur(tmp_path)
    p = calistir(tmp_path, kok)
    yeni = yeni_snapshotlar(kok)
    assert len(yeni) == 1 and re.fullmatch(r"ai-arz-serisi-\d{8}T\d{6}Z\.ndjson", yeni[0])
    kopya = kok / "archive" / yeni[0]
    assert kopya.read_bytes() == (kok / "ai-arz-serisi.ndjson").read_bytes() == b'{"a": 1}\n'
    assert "frozen copy: %s (1 lines)" % yeni[0] in p.stdout


def test_snapshot_name_uses_the_utc_clock(tmp_path):
    kok, _ = kur(tmp_path)
    p = calistir(tmp_path, kok, TZ="Asia/Tokyo")
    ad = yeni_snapshotlar(kok)[0]
    gun = re.search(r"(\d{8})T(\d\d)", ad)
    log = re.search(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d)", p.stdout, re.M)
    assert gun.group(1) == "".join(log.groups()[:3]) and gun.group(2) == log.group(4)


def test_snapshot_is_stamped_and_the_stamp_rc_is_logged(tmp_path):
    kok, kayit = kur(tmp_path, rc_ots=1)
    p = calistir(tmp_path, kok)
    ad = yeni_snapshotlar(kok)[0]
    ots = oku(kayit, "ots.json")
    assert ots == ["ots", "stamp", str(kok / "archive" / ad)]
    assert (kok / "archive" / (ad + ".ots")).read_bytes() == b"proof"
    assert "STEP-2 rc=1 seal=%s.ots" % ad in p.stdout


def test_empty_series_is_not_stamped(tmp_path):
    kok, kayit = kur(tmp_path, satir=None)
    (kok / "ai-arz-serisi.ndjson").write_text("")
    p = calistir(tmp_path, kok)
    assert yeni_snapshotlar(kok) == [] and oku(kayit, "ots.json") is None
    assert "STEP-2 SKIPPED (collection failed or series empty)" in p.stdout


def test_failed_collection_is_not_stamped(tmp_path):
    kok, kayit = kur(tmp_path, rc_toplayici=1)
    p = calistir(tmp_path, kok)
    assert yeni_snapshotlar(kok) == [] and oku(kayit, "ots.json") is None
    assert "STEP-2 SKIPPED" in p.stdout


def test_archive_folder_is_created_when_missing(tmp_path):
    kok, _ = kur(tmp_path)
    (kok / "archive").rmdir()
    calistir(tmp_path, kok)
    assert len(yeni_snapshotlar(kok)) == 1


# ── step 3: audit ───────────────────────────────────────────────────────────
def test_watchdog_gets_the_ledger_and_the_newest_earlier_snapshot(tmp_path):
    arsiv = [("ai-arz-serisi-20260901T070000Z.ndjson", "x\n"),
             ("ai-arz-serisi-20260920T070000Z.ndjson", "x\n"),
             ("ai-arz-serisi-20260920T070000Z.ndjson.ots", "p"),
             ("notes.ndjson", "n\n"),
             ("ai-arz-serisi-20260910T070000Z.ndjson", "x\n")]
    kok, kayit = kur(tmp_path, arsiv=arsiv)
    calistir(tmp_path, kok)
    assert oku(kayit, "bekci.json") == [
        "--ledger", str(tmp_path / "home" / "logs" / "ai-arz-alarm.ndjson"),
        "--previous", str(kok / "archive" / "ai-arz-serisi-20260920T070000Z.ndjson")]


def test_watchdog_gets_an_empty_previous_when_no_snapshot_exists(tmp_path):
    kok, kayit = kur(tmp_path)
    calistir(tmp_path, kok)
    assert oku(kayit, "bekci.json")[2:] == ["--previous", ""]


def test_watchdog_runs_even_when_collection_fails(tmp_path):
    kok, kayit = kur(tmp_path, rc_toplayici=1)
    calistir(tmp_path, kok)
    assert oku(kayit, "bekci.json") is not None


# ── log and exit ────────────────────────────────────────────────────────────
def test_every_log_line_has_a_utc_time_and_each_step_logs_its_rc(tmp_path):
    kok, _ = kur(tmp_path, rc_toplayici=3, rc_bekci=1)
    p = calistir(tmp_path, kok)
    satirlar = p.stdout.splitlines()
    assert satirlar and all(DAMGA.match(s) for s in satirlar)
    for parca in ("=== STEP-1 COLLECT ===", "STEP-1 rc=3", "=== STEP-2 STAMP (frozen snapshot) ===",
                  "=== STEP-3 AUDIT (freshness watchdog) ===", "STEP-3 rc=1 (0=GREEN 1=YELLOW 2=RED)",
                  "=== DONE collect=3 watchdog=1 exit=3 ==="):
        assert any(s.endswith(parca) for s in satirlar), parca
    assert p.returncode == 3


@pytest.mark.parametrize("rc_t, rc_b, beklenen", [(0, 1, 0), (3, 1, 3), (0, 3, 0), (1, 1, 1)])
def test_exit_code_for_yellow_and_other_watchdog_codes(tmp_path, rc_t, rc_b, beklenen):
    kok, _ = kur(tmp_path, rc_toplayici=rc_t, rc_bekci=rc_b)
    assert calistir(tmp_path, kok).returncode == beklenen


def test_an_unset_variable_stops_the_run(tmp_path):
    kok, kayit = kur(tmp_path)
    ortam = {k: v for k, v in os.environ.items() if k != "HOME"}
    ortam["PYTHONPATH"] = str(tmp_path / "ots")
    p = subprocess.run(["bash", str(kok / "run_weekly.sh")], cwd=tmp_path, env=ortam,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0 and "HOME: unbound variable" in p.stderr
    assert oku(kayit, "bekci.json") is None
