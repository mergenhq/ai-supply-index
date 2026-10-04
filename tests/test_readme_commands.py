"""Every command line in the README names a script that exists and only flags that script accepts.
The scripts are asked for --help only; nothing is collected or written."""
import re
import subprocess
import sys

import pytest

from conftest import KOK

README = (KOK / "README.md").read_text(encoding="utf-8")
KOMUT = re.compile(r"python3 ((?:examples/)?[\w./-]+\.py)((?:\s+--[\w-]+(?:\s+[\w./-]+)?)*)")


def komutlar():
    out = []
    for m in KOMUT.finditer(README):
        bayraklar = re.findall(r"--[\w-]+", m.group(2))
        out.append((m.group(1), tuple(bayraklar)))
    return sorted(set(out))


KOMUTLAR = komutlar()


def test_the_readme_has_command_lines():
    adlar = {k for k, _ in KOMUTLAR}
    assert {"collector.py", "freshness_watchdog.py", "to_english.py"} <= adlar


@pytest.mark.parametrize("betik,bayraklar", KOMUTLAR, ids=lambda x: x if isinstance(x, str) else " ".join(x))
def test_command_names_an_existing_script_and_accepted_flags(betik, bayraklar):
    yol = KOK / betik
    assert yol.exists(), betik
    yardim = subprocess.run([sys.executable, str(yol), "--help"], cwd=KOK, capture_output=True, text=True,
                            timeout=60)
    assert yardim.returncode == 0, yardim.stderr
    for b in bayraklar:
        assert re.search(r"(^|[\s,\[])%s\b" % re.escape(b), yardim.stdout), "%s does not accept %s" % (betik, b)


def test_exit_codes_named_in_the_readme_match_the_scripts():
    import collector as c
    satir = next(s for s in README.splitlines() if "python3 collector.py --out" in s)
    assert "exit 0=all OK 3=partial 1=none" in satir and c.KISMI == 3
    satir = next(s for s in README.splitlines() if s.startswith("python3 freshness_watchdog.py"))
    assert "0=green 1=yellow 2=red" in satir
