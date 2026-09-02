"""Tests for the Music Assistant MediaProvider plugin (network-free)."""
import json
from os.path import dirname, join
from unittest.mock import MagicMock, patch

from mediavocab import MediaType, Release, Signals

from ovos_media_provider_mass import MAssMediaProvider, score_release

FIXTURES = join(dirname(__file__), "fixtures")


def _search_fixture():
    with open(join(FIXTURES, "search_worms.json")) as f:
        return json.load(f)


def _provider_with_mock(search_return=None):
    prov = MAssMediaProvider({"url": "http://mass.local:8095"})
    api = MagicMock()
    api.search_media.return_value = search_return if search_return is not None else _search_fixture()
    prov._api = api
    return prov, api


def test_instantiation():
    assert MAssMediaProvider.name == "music_assistant"
    assert MAssMediaProvider.SERVED_MEDIA == {
        MediaType.MUSIC, MediaType.RADIO, MediaType.PODCAST, MediaType.AUDIOBOOK
    }


def test_search_without_url_returns_empty():
    prov = MAssMediaProvider()
    assert prov.api is None


def test_token_reaches_client_constructor():
    prov = MAssMediaProvider({"url": "http://mass.local:8095", "token": "sekrit-token"})
    with patch("ovos_media_provider_mass.SimpleHTTPMusicAssistantClient") as mock_client:
        assert prov.api is mock_client.return_value
    mock_client.assert_called_once_with("http://mass.local:8095", token="sekrit-token")


def test_no_token_passes_none_to_client_constructor():
    prov = MAssMediaProvider({"url": "http://mass.local:8095"})
    with patch("ovos_media_provider_mass.SimpleHTTPMusicAssistantClient") as mock_client:
        assert prov.api is mock_client.return_value
    mock_client.assert_called_once_with("http://mass.local:8095", token=None)
    assert prov.search(Signals(title="worms")) == []


def test_search_empty_query_returns_empty():
    prov, api = _provider_with_mock()
    assert prov.search(Signals(title="")) == []
    api.search_media.assert_not_called()


def test_search_returns_scored_releases():
    prov, api = _provider_with_mock()
    results = prov.search(Signals(title="worms"))

    api.search_media.assert_called_once_with("worms", limit=10)
    assert results and all(isinstance(r, Release) for r in results)
    assert all(0.0 <= r.match_confidence <= 1.0 for r in results)
    # exact title match should outrank a partial one
    by_title = {r.work.title: r.match_confidence for r in results}
    assert by_title["Worms"] > by_title["Food for the Worms"]
    # every result carries a playable library:// uri
    assert all(r.uri.startswith("library://") for r in results)


def test_search_narrows_to_requested_medium():
    prov, _ = _provider_with_mock()
    radio_only = prov.search(Signals(title="worms", medium=MediaType.RADIO))
    assert radio_only
    assert all(r.work.media_type == MediaType.RADIO for r in radio_only)

    music_only = prov.search(Signals(title="worms", medium=MediaType.MUSIC))
    assert all(r.work.media_type == MediaType.MUSIC for r in music_only)


def test_search_generic_medium_returns_all_types():
    prov, _ = _provider_with_mock()
    results = prov.search(Signals(title="worms", medium=MediaType.GENERIC))
    kinds = {r.work.media_type for r in results}
    assert MediaType.MUSIC in kinds
    assert MediaType.RADIO in kinds
    assert MediaType.PODCAST in kinds


def test_search_swallows_backend_error():
    prov, api = _provider_with_mock()
    api.search_media.side_effect = RuntimeError("boom")
    assert prov.search(Signals(title="x")) == []


def test_score_release_favorite_and_artist_bonus():
    fav = score_release(
        _make_release("Worms", artist="Viagra Boys", favorite=True),
        Signals(title="worms", artist="viagra boys"),
    )
    plain = score_release(
        _make_release("Worms"),
        Signals(title="worms"),
    )
    assert fav >= plain


def _make_release(title, artist=None, favorite=False):
    from mediavocab import Work
    extra = {}
    if artist:
        extra["artist"] = artist
    if favorite:
        extra["favorite"] = True
    return Release(work=Work(title=title, media_type=MediaType.MUSIC, extra=extra),
                   uri="library://track/1")
