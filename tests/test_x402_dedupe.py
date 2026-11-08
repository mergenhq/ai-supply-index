"""Tests for the x402 walk's de-duplication and per-page total, with the network mocked: each call
to `cek` returns the next prepared (items, total) page."""
import pytest

import collector as c


def it(rid, calls=5, payers=1):
    d = {"quality": {"l30DaysTotalCalls": calls, "l30DaysUniquePayers": payers}}
    if rid is not None:
        d["resource"] = rid
    return d


def page(prefix, n):
    return [it("%s%d" % (prefix, i)) for i in range(n)]


@pytest.fixture
def walk(monkeypatch):
    def run(pages):
        urls = []

        def cek(url, ham=False):
            i = len(urls)
            urls.append(url)
            assert i < len(pages), "unexpected extra page"
            items, total = pages[i]
            return 200, {"items": items, "pagination": {"total": total}}
        monkeypatch.setattr(c, "cek", cek)
        monkeypatch.setattr(c.time, "sleep", lambda s: None)
        return c.uc_x402()
    return run


def test_entry_repeated_across_a_page_boundary_is_counted_once(walk):
    a = page("r", 500)
    b = [a[-1]] + page("s", 99)
    o = walk([(a, 599), (b, 599)])
    assert o["taranan"] == 599 and o["cift_sayilan"] == 1
    assert "kaynak_degisti" not in o


def test_total_is_read_on_every_page_and_the_last_one_wins(walk):
    o = walk([(page("r", 500), 600), (page("s", 130), 630)])
    assert o["kaynak_sayisi_ilk"] == 600 and o["kaynak_sayisi_son"] == 630
    assert o["kaynak_sayisi"] == 630 and o["taranan"] == 630 and o["sayfa"] == 2
    assert "kaynak_degisti" not in o


def test_scan_still_past_the_total_is_marked_with_the_gap(walk):
    o = walk([(page("r", 500), 600), (page("s", 110), 600)])
    assert o["taranan"] == 610 and o["cift_sayilan"] == 0
    assert o["kaynak_degisti"] is True and o["kaynak_fark"] == 10
    assert o["taranan"] - o["kaynak_sayisi"] == o["kaynak_fark"]


def test_entries_without_resource_are_counted_and_tallied(walk):
    o = walk([(page("r", 3) + [it(None), it(None), it("")], 6)])
    assert o["kimliksiz"] == 3 and o["taranan"] == 6 and o["cift_sayilan"] == 0


def test_single_page_summary_is_unchanged_in_shape(walk):
    o = walk([([it("a", 0, 0), it("b", 5, 1), it("c", 50, 3), it("d", 5000, 20)], 4)])
    assert o["kaynak_sayisi"] == 4 and o["taranan"] == 4 and o["sayfa"] == 1
    assert o["cift_sayilan"] == 0 and o["kimliksiz"] == 0
    assert "kaynak_degisti" not in o and "olculemedi" not in o
    assert o["top10_cagri"][0] == {"cagri": 5000, "kaynak": "d"}


def test_empty_page_stops_the_walk(walk):
    o = walk([(page("r", 500), 5000), ([], 5000)])
    assert o["sayfa"] == 2 and o["taranan"] == 500
