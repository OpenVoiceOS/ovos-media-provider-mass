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

Uses ovoscope's ``MediaProviderHarness``, which discovers the provider through its
real ``opm.media.provider`` entry-point and drives the path the OCP pipeline takes
— discover -> ``serves()`` context gate -> ``search_safe`` — with the Music
Assistant client mocked.
"""
import json
import unittest
from os.path import dirname, join
from unittest.mock import MagicMock

from mediavocab import MediaType, Release, Signals
from mediavocab.taxonomy import PlaybackType
from ovos_plugin_manager.templates.media_provider import MediaProvider, QueryContext

from ovoscope import MediaProviderHarness

PROVIDER_NAME = "music_assistant"
FIXTURES = join(dirname(dirname(__file__)), "fixtures")


def _search_fixture() -> dict:
    with open(join(FIXTURES, "search_worms.json")) as f:
        return json.load(f)


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
    """Drive the provider via MediaProviderHarness (discover -> gate -> search)."""

    def setUp(self):
        self.api = _mock_api()
        self.h = MediaProviderHarness.from_entrypoint(
            PROVIDER_NAME,
            config={"url": "http://mass.local:8095", "max_results": 10},
            mock_api=self.api,
        )
        self.provider = self.h.provider

    # -- discovery ---------------------------------------------------------

    def test_entry_point_resolves_to_provider(self):
        self.h.assert_entrypoint_registered()
        self.assertIsInstance(self.provider, MediaProvider)
        self.assertEqual(self.provider.name, PROVIDER_NAME)
        self.assertEqual(self.provider.playback_type, {PlaybackType.AUDIO})
        self.assertEqual(
            self.provider.media,
            {MediaType.MUSIC, MediaType.RADIO, MediaType.PODCAST, MediaType.AUDIOBOOK},
        )

    def test_is_available_pings_server(self):
        self.assertTrue(self.h.is_available())
        self.api.get_players.assert_called_once()

    # -- routing / context gate -------------------------------------------

    def test_serves_on_audio_device(self):
        self.h.assert_routes(Signals(medium=MediaType.MUSIC),
                             QueryContext(supported_playback_types={"audio"}))

    def test_not_served_on_video_only_device(self):
        self.h.assert_not_routes(Signals(medium=MediaType.MUSIC),
                                 QueryContext(supported_playback_types={"video"}))

    def test_not_served_for_unsupported_medium(self):
        self.h.assert_not_routes(Signals(medium=MediaType.MOVIE))

    # -- the full search path the pipeline calls ---------------------------

    def test_search_safe_returns_scored_playables(self):
        results = self.h.assert_returns_playables(Signals(title="worms"))
        self.api.search_media.assert_called_once_with("worms", limit=10)
        # exact title outranks the partial match -> ranking is meaningful
        by_title = {r.work.title: r.match_confidence for r in results}
        self.assertGreater(by_title["Worms"], by_title["Food for the Worms"])
        self.assertTrue(all(r.uri.startswith("library://") for r in results))
        self.assertTrue(all(isinstance(r, Release) for r in results))

    def test_search_safe_swallows_backend_error(self):
        self.api.search_media.side_effect = RuntimeError("server exploded")
        self.assertEqual(self.h.search_safe(Signals(title="worms")), [])

    def test_search_narrows_to_requested_medium(self):
        radio = self.h.search_safe(Signals(title="worms", medium=MediaType.RADIO))
        self.assertTrue(radio)
        self.assertTrue(all(r.work.media_type == MediaType.RADIO for r in radio))

    # -- featured / home content ------------------------------------------

    def test_featured_media_from_recently_played(self):
        feats = self.h.featured_media()
        self.assertEqual([r.work.title for r in feats], ["Recent Hit"])


if __name__ == "__main__":
    unittest.main()
