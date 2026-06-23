"""Tests for the Music Assistant MediaProvider plugin (network-free)."""
import json
from os.path import dirname, join
from unittest.mock import MagicMock

from mediavocab import MediaType, Release, Signals
from mediavocab.taxonomy import PlaybackType

from ovos_media_provider_mass import MAssMediaProvider, score_release

FIXTURES = join(dirname(__file__), "fixtures")


def _search_fixture():
    with open(join(FIXTURES, "search_worms.json")) as f:
        return json.load(f)


def _provider_with_mock(search_return=None, recently=None):
    prov = MAssMediaProvider({"url": "http://mass.local:8095"})
    api = MagicMock()
    api.search_media.return_value = search_return if search_return is not None else _search_fixture()
    api.recently_played.return_value = recently if recently is not None else []
    prov._api = api
    return prov, api


def test_instantiation_and_routing():
    assert MAssMediaProvider.name == "music_assistant"
    assert MAssMediaProvider.media == {
        MediaType.MUSIC, MediaType.RADIO, MediaType.PODCAST, MediaType.AUDIOBOOK
    }
    assert MAssMediaProvider.playback_type == {PlaybackType.AUDIO}


def test_matches_served_types_true():
    prov = MAssMediaProvider()
    assert prov.matches(Signals(medium=MediaType.MUSIC)) is True
    assert prov.matches(Signals(medium=MediaType.RADIO)) is True
    assert prov.matches(Signals(medium=MediaType.PODCAST)) is True
    assert prov.matches(Signals(medium=MediaType.AUDIOBOOK)) is True


def test_matches_unserved_type_false():
    prov = MAssMediaProvider()
    assert prov.matches(Signals(medium=MediaType.MOVIE)) is False


def test_is_available_false_without_url():
    prov = MAssMediaProvider()
    assert prov.api is None
    assert prov.is_available() is False


def test_is_available_true_when_server_answers():
    prov, api = _provider_with_mock()
    api.get_players.return_value = []
    assert prov.is_available() is True
    api.get_players.assert_called_once()


def test_is_available_false_when_server_errors():
    prov, api = _provider_with_mock()
    api.get_players.side_effect = RuntimeError("connection refused")
    assert prov.is_available() is False


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


def test_featured_media_maps_recently_played():
    recent = [{
        "media_type": "track", "name": "Recent Hit", "uri": "library://track/55",
        "is_playable": True, "artists": [{"name": "Someone"}],
    }]
    prov, _ = _provider_with_mock(recently=recent)
    feats = prov.featured_media()
    assert [r.work.title for r in feats] == ["Recent Hit"]


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
