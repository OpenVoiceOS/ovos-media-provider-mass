"""Opt-in live test against a real Music Assistant server.

Skipped unless ``MASS_SERVER_URL`` points at a reachable server::

    MASS_SERVER_URL=http://192.168.1.100:8095 pytest test/live/
"""
import os

import pytest

from mediavocab import MediaType, Release, Signals

from ovos_media_provider_mass import MAssMediaProvider

MASS_SERVER_URL = os.environ.get("MASS_SERVER_URL")

pytestmark = pytest.mark.skipif(
    not MASS_SERVER_URL, reason="set MASS_SERVER_URL to run live Music Assistant tests"
)


@pytest.fixture(scope="module")
def provider():
    return MAssMediaProvider({"url": MASS_SERVER_URL, "max_results": 5})


def test_live_search(provider):
    results = provider.search(Signals(title="the beatles", medium=MediaType.MUSIC))
    assert all(isinstance(r, Release) for r in results)
    for r in results:
        assert r.uri.startswith("library://")
        assert r.work.media_type == MediaType.MUSIC
        assert 0.0 <= r.match_confidence <= 1.0
