"""Tests for the x402 page limit in collector.py, with the network mocked: the registry is served
page by page from memory, 500 resources per page, as the discovery endpoint does."""
import pytest

import collector as c

PAGE = 500


@pytest.fixture
def registry(monkeypatch):
    """Serve a registry of `total` resources; returns the list of requested offsets."""
    calls = []

    def serve(total):
        def cek(url, ham=False):
            offset = int(url.rsplit("=", 1)[1])
            calls.append(offset)
            items = [{"resource": "r%d" % i, "quality": {"l30DaysTotalCalls": 1 + i % 7, "l30DaysUniquePayers": 1}}
                     for i in range(offset, min(offset + PAGE, total))]
            return 200, {"items": items, "pagination": {"total": total}}
        monkeypatch.setattr(c, "cek", cek)
        monkeypatch.setattr(c.time, "sleep", lambda s: None)
        return calls
    return serve


def test_limit_is_200_pages_of_500():
    assert c.X402_SAYFA_TAVANI == 200 and c.X402_SAYFA_TAVANI * PAGE == 100000


def test_registry_of_34419_resources_is_walked_completely(registry):
    calls = registry(34419)
    o = c.uc_x402()
    assert len(calls) == 69 and o["sayfa"] == 69
    assert o["kaynak_sayisi"] == 34419 and o["taranan"] == 34419
    assert o["cagri_30g"]["n"] == 34419 and o["odeyen_30g"]["n"] == 34419
    assert "olculemedi" not in o


def test_registry_larger_than_the_limit_stops_at_200_pages_with_olculemedi(registry):
    calls = registry(100001)
    o = c.uc_x402()
    assert len(calls) == 200 and o["sayfa"] == 200 and o["taranan"] == 100000
    assert "page cap reached" in o["olculemedi"] and "100001" in o["olculemedi"]


def test_registry_of_exactly_200_pages_has_no_olculemedi(registry):
    calls = registry(200 * PAGE)
    o = c.uc_x402()
    assert len(calls) == 200 and o["taranan"] == 100000
    assert "olculemedi" not in o
