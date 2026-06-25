# Copyright 2025 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""End-to-end test for the Music Assistant MediaProvider.

There is no ovoscope harness for *search providers* (ovoscope's media harness
drives the OCP **player** state-machine, not the catalog half), so the genuine
end-to-end surface for a provider is the path the OCP pipeline actually takes:

1. **discover** the plugin through its published ``opm.media.provider``
   entry-point (not by importing the class directly — that is what the unit
   tests do);
2. **gate** it with :meth:`MediaProvider.serves` against a :class:`QueryContext`
   (device capabilities + content policy), exactly as the pipeline does before
   paying for a search;
3. **search** through :meth:`MediaProvider.search_safe` — the never-raising entry
   the pipeline's thread-pool dispatch calls — and get scored, playable
   ``mediavocab.Release`` objects back;
4. surface **featured media**.

The Music Assistant HTTP client is mocked, so no server or network is required.
"""
import json
import unittest
from importlib.metadata import entry_points
from os.path import dirname, join
from unittest.mock import MagicMock

from mediavocab import MediaType, Release, Signals
from mediavocab.taxonomy import PlaybackType
from ovos_plugin_manager.templates.media_provider import MediaProvider, QueryContext

ENTRY_POINT_GROUP = "opm.media.provider"
PROVIDER_NAME = "music_assistant"
FIXTURES = join(dirname(dirname(__file__)), "fixtures")


def _search_fixture() -> dict:
    with open(join(FIXTURES, "search_worms.json")) as f:
        return json.load(f)


def _load_provider_class():
    """Resolve the provider class through real entry-point discovery."""
    eps = entry_points(group=ENTRY_POINT_GROUP)
    match = [ep for ep in eps if ep.name == PROVIDER_NAME]
    assert match, (
        f"no {ENTRY_POINT_GROUP!r} entry-point named {PROVIDER_NAME!r} is "
        f"installed — is the package installed (pip install -e .)?"
    )
    return match[0].load()


def _mock_api(recently=None) -> MagicMock:
    api = MagicMock()
    api.search_media.return_value = _search_fixture()
    api.get_players.return_value = []
    api.recently_played.return_value = recently or [{
        "media_type": "track", "name": "Recent Hit", "uri": "library://track/55",
        "is_playable": True, "artists": [{"name": "Someone"}],
    }]
    return api


class TestMAssProviderEndToEnd(unittest.TestCase):
    """Drive the provider the way the OCP pipeline does: discover → gate → search."""

    def setUp(self):
        self.cls = _load_provider_class()
        self.api = _mock_api()
        self.provider: MediaProvider = self.cls({"url": "http://mass.local:8095",
                                                 "max_results": 10})
        # inject the mocked client (bypass the lazy real HTTP client)
        self.provider._api = self.api

    # -- discovery ---------------------------------------------------------

    def test_entry_point_resolves_to_provider(self):
        """The published opm.media.provider entry-point loads our class."""
        self.assertTrue(issubclass(self.cls, MediaProvider))
        self.assertEqual(self.cls.name, PROVIDER_NAME)
        self.assertEqual(self.cls.playback_type, {PlaybackType.AUDIO})
        self.assertEqual(
            self.cls.media,
            {MediaType.MUSIC, MediaType.RADIO, MediaType.PODCAST, MediaType.AUDIOBOOK},
        )

    def test_is_available_pings_server(self):
        self.assertTrue(self.provider.is_available())
        self.api.get_players.assert_called_once()

    # -- routing / context gate -------------------------------------------

    def test_serves_on_audio_device(self):
        """An audio-capable device with no content policy is served music."""
        ctx = QueryContext(supported_playback_types={"audio"})
        self.assertTrue(self.provider.serves(Signals(medium=MediaType.MUSIC), ctx))

    def test_not_served_on_video_only_device(self):
        """A video-only device cannot render this AUDIO provider → skipped."""
        ctx = QueryContext(supported_playback_types={"video"})
        self.assertFalse(self.provider.serves(Signals(medium=MediaType.MUSIC), ctx))

    def test_not_served_for_unsupported_medium(self):
        self.assertFalse(self.provider.serves(Signals(medium=MediaType.MOVIE)))

    # -- the full search path the pipeline calls ---------------------------

    def test_search_safe_returns_scored_playables(self):
        """search_safe (the pipeline's never-raising entry) returns ranked,
        playable Releases for a real query."""
        results = self.provider.search_safe(Signals(title="worms"))
        self.api.search_media.assert_called_once_with("worms", limit=10)

        self.assertTrue(results)
        self.assertTrue(all(isinstance(r, Release) for r in results))
        self.assertTrue(all(0.0 <= r.match_confidence <= 1.0 for r in results))
        self.assertTrue(all(r.uri.startswith("library://") for r in results))

        # exact title outranks the partial match → ranking is meaningful
        by_title = {r.work.title: r.match_confidence for r in results}
        self.assertGreater(by_title["Worms"], by_title["Food for the Worms"])

    def test_search_safe_swallows_backend_error(self):
        """A misbehaving server must not abort a multi-provider search."""
        self.api.search_media.side_effect = RuntimeError("server exploded")
        self.assertEqual(self.provider.search_safe(Signals(title="worms")), [])

    def test_search_narrows_to_requested_medium(self):
        radio = self.provider.search_safe(Signals(title="worms", medium=MediaType.RADIO))
        self.assertTrue(radio)
        self.assertTrue(all(r.work.media_type == MediaType.RADIO for r in radio))

    # -- featured / home content ------------------------------------------

    def test_featured_media_from_recently_played(self):
        feats = self.provider.featured_media()
        self.assertEqual([r.work.title for r in feats], ["Recent Hit"])


if __name__ == "__main__":
    unittest.main()
