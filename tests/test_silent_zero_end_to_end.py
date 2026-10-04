"""End to end: an upstream response the collector cannot use must end as a RED watchdog finding that
names the endpoint, never as a quiet GREEN (README, "The silent-zero brake"). The collector's real
endpoint functions read fake responses; the other endpoints return healthy summaries; the run is
written to tmp_path and audited by the real watchdog. No network, fixed clock."""
import urllib.error
from datetime import timedelta

import pytest

import collector as c
import freshness_watchdog as w
from conftest import SIMDI, sabit_datetime

FONKSIYON = {u[0]: u[1] for u in c.UCLAR}

# endpoint -> responses of the wrong shape (each one is tried on its own)
BOZUK = {
    "x402_discovery": [{"resources": []}, {"items": [], "pagination": {}}],
    "sherlock_leaderboard": [[{"handle": "a"}], "html"],
    "sherlock_contests": [{"contests": []}, {"items": [{"id": 1, "ends_at": "soon"}], "total": 1}],
    "code4rena_audits": [{"audits": []}, {"data": {"audits": [{"endTime": "later"}]}, "pagination": {}}],
    "defillama_fees_ai_agents": [{"protocols": []}, {}],
    "defillama_summary_virtuals": [{}, {"totalDataChart": []}],
    "apify_store": [{"data": {}}, {"items": []}],
    "hf_models": [{"models": []}, {}],
    "npm_downloads": [{}, {"downloads": [{"day": "2026-08-17"}]}],
    "pypi_downloads": [{}, {"data": []}],
    "github_repos": [{}, {"message": "Not Found"}],
}
HATALAR = [urllib.error.HTTPError("u", 503, "x", None, None), urllib.error.URLError("down"), TimeoutError("t")]


def calistir(tmp_path, monkeypatch, hedef, yanit):
    def cek(url, ham=False):
        if isinstance(yanit, Exception):
            raise yanit
        return 200, yanit
    monkeypatch.setattr(c, "cek", cek)
    monkeypatch.setattr(c.time, "sleep", lambda s: None)
    monkeypatch.setattr(c, "datetime", sabit_datetime(SIMDI))
    uclar = [(ad, FONKSIYON[ad], "") if ad == hedef else (ad, (lambda o=o: o), "")
             for ad, o in w._SAGLAM.items()]
    monkeypatch.setattr(c, "UCLAR", uclar)
    seri = tmp_path / "seri.ndjson"
    c.main(["--out", str(seri)])
    return w.denetle(seri, SIMDI + timedelta(hours=1))


def test_every_collector_endpoint_is_covered():
    assert set(BOZUK) == set(FONKSIYON) == set(w._SAGLAM)


def test_a_healthy_run_is_green(tmp_path, monkeypatch, capsys):
    kod, r = calistir(tmp_path, monkeypatch, None, None)
    assert kod == 0, r["findings"]


@pytest.mark.parametrize("uc,yanit", [(uc, y) for uc, ys in sorted(BOZUK.items()) for y in ys],
                         ids=lambda x: x if isinstance(x, str) and x in BOZUK else "")
def test_a_response_of_the_wrong_shape_is_red_for_its_endpoint(tmp_path, monkeypatch, capsys, uc, yanit):
    kod, r = calistir(tmp_path, monkeypatch, uc, yanit)
    assert kod == 2, r["findings"]
    assert any(b.startswith("RED ") and uc in b for b in r["findings"]), r["findings"]


@pytest.mark.parametrize("uc", sorted(BOZUK))
@pytest.mark.parametrize("hata", HATALAR, ids=lambda e: type(e).__name__)
def test_an_http_or_network_failure_is_red_for_its_endpoint(tmp_path, monkeypatch, capsys, uc, hata):
    kod, r = calistir(tmp_path, monkeypatch, uc, hata)
    assert kod == 2, r["findings"]
    assert any(b.startswith("RED ") and uc in b for b in r["findings"]), r["findings"]
