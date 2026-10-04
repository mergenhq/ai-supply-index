"""Tests for run_weekly.sh: the script runs in a copy of the repository layout where
collector.py and freshness_watchdog.py are stubs that exit with chosen codes."""
import os
import shutil
import subprocess

import pytest

from conftest import KOK


def calistir(tmp_path, rc_toplayici, rc_bekci):
    kok = tmp_path / "repo"
    kok.mkdir()
    shutil.copy(KOK / "run_weekly.sh", kok / "run_weekly.sh")
    (kok / "collector.py").write_text(
        "import sys\nopen('ai-arz-serisi.ndjson','a').write('{}\\n')\nsys.exit(%d)\n" % rc_toplayici)
    (kok / "freshness_watchdog.py").write_text(
        "import sys\nopen(%r,'w').write(' '.join(sys.argv[1:]))\nsys.exit(%d)\n"
        % (str(tmp_path / "bekci_argv"), rc_bekci))
    ortam = dict(os.environ, HOME=str(tmp_path))
    p = subprocess.run(["bash", str(kok / "run_weekly.sh")], cwd=kok, env=ortam,
                       capture_output=True, text=True, timeout=60)
    return p, kok


@pytest.mark.parametrize("rc_t, rc_b, beklenen", [
    (0, 0, 0),   # all collected, watchdog green
    (0, 1, 0),   # yellow does not fail the run
    (0, 2, 2),   # red watchdog fails the run
    (3, 0, 3),   # partial collection
    (3, 2, 2),   # red wins over partial
    (1, 0, 1),   # nothing collected
    (1, 2, 1),   # nothing collected wins
])
def test_exit_code(tmp_path, rc_t, rc_b, beklenen):
    p, _ = calistir(tmp_path, rc_t, rc_b)
    assert p.returncode == beklenen, p.stdout + p.stderr


@pytest.mark.parametrize("rc_t, arsiv", [(0, True), (3, True), (1, False)])
def test_snapshot_taken_for_full_and_partial_runs(tmp_path, rc_t, arsiv):
    _, kok = calistir(tmp_path, rc_t, 0)
    assert bool(list((kok / "archive").glob("*.ndjson"))) == arsiv
