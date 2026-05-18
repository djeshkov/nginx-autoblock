"""Shared pytest fixtures."""
import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def autoblock_mod():
    """Import the `autoblock` script as a module (it has no .py extension)."""
    loader = SourceFileLoader("autoblock", str(ROOT / "autoblock"))
    spec = importlib.util.spec_from_loader("autoblock", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["autoblock"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture
def base_ip_stats():
    """A neutral per-IP stats dict — looks like a typical real user.

    Tests override individual fields to simulate bot signals.
    """
    return {
        "reqs": 30,
        "assets": 18,           # 60% assets — typical real browser
        "no_ref": 2,            # mostly internal referers
        "ext_ref": 1,
        "int_ref": 27,
        "status_4xx": 1,
        "paths": {f"/p{i}" for i in range(8)},  # 8 distinct paths in 30 reqs
        "ua_set": {"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"},
    }


@pytest.fixture
def scraper_ip_stats():
    """A neutral per-IP stats dict for a distributed scraper — minimum signals
    that should trip ban classification."""
    return {
        "reqs": 3,
        "assets": 0,
        "no_ref": 3,
        "ext_ref": 0,
        "int_ref": 0,
        "status_4xx": 0,
        "paths": {"/reservation/c0303179-0ff8-4c47-98fd-561463ff45d1",
                  "/reservation/f3675a56-4a60-40c8-99d3-aa316755b56a",
                  "/reservation/b70d8633-4f6c-4ea0-8e2f-2483b6d30b89"},
        "ua_set": {"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    }


@pytest.fixture
def base_ua_cluster_stats():
    """A UA-cluster stats dict for a genuinely popular real browser:
    many IPs share a current Chrome UA, but they load assets and send referers.

    Tests override fields to simulate a botnet cluster.
    """
    return {
        "ua":         "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "ip_count":   200,
        "reqs":       4000,
        "assets":     2400,   # 60% asset ratio — real browsers
        "no_ref":     400,    # 10% no-referer
        "status_4xx": 40,     # 1% 4xx
    }


@pytest.fixture
def botnet_ua_cluster_stats():
    """A UA-cluster stats dict matching the May 18 2026 distributed-scraping
    incident: a large fleet of hosting IPs sharing one plausible Firefox UA,
    loading no assets and sending no referers."""
    return {
        "ua":         "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
        "ip_count":   250,
        "reqs":       3000,
        "assets":     0,      # 0% asset ratio
        "no_ref":     2900,   # 97% no-referer
        "status_4xx": 100,    # ~3% 4xx
    }
