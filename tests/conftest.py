"""Shared fixtures. The suite must never touch the network, the wall clock or files
outside tmp_path; the autouse fixture below turns any outbound connection into a failure."""
import socket
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

# fixed "now" used across the suite (the same instant the watchdog self-test uses)
SIMDI = datetime(2026, 8, 18, 15, 0, tzinfo=timezone.utc)


class AgYasak(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def ag_yok(monkeypatch):
    def engel(*a, **k):
        raise AgYasak("network access attempted during tests")
    monkeypatch.setattr(socket.socket, "connect", engel)
    monkeypatch.setattr(socket, "create_connection", engel)
    monkeypatch.setattr(urllib.request, "urlopen", engel)


def sabit_datetime(simdi):
    """A datetime subclass whose now() is frozen at `simdi`."""
    class SabitDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return simdi if tz is None else simdi.astimezone(tz)
    return SabitDT
