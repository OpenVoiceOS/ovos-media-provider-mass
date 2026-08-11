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

Uses ovoscope's ``MediaProviderHarness`` to discover the provider through its
real ``opm.media.provider`` entry-point (the packaging signal the OCP pipeline
relies on) and then drives the simplified contract — a single ``search()`` call
— with the Music Assistant client mocked.
"""
import json
import unittest
from os.path import dirname, join
from unittest.mock import MagicMock

from mediavocab import MediaType, Release, Signals
from ovos_plugin_manager.templates.media_provider import MediaProvider

from ovoscope import MediaProviderHarness

PROVIDER_NAME = "music_assistant"
FIXTURES = join(dirname(dirname(__file__)), "fixtures")


def _search_fixture() -> dict:
    with open(join(FIXTURES, "search_worms.json")) as f:
        return json.load(f)


def _mock_api() -> MagicMock:
    api = MagicMock()
    api.search_media.return_value = _search_fixture()
    return api


class TestMAssProviderEndToEnd(unittest.TestCase):
    """Discover the provider via its entry-point and drive ``search()``."""

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
        self.assertEqual(
            self.provider.SERVED_MEDIA,
            {MediaType.MUSIC, MediaType.RADIO, MediaType.PODCAST, MediaType.AUDIOBOOK},
        )

    # -- the search path the pipeline calls --------------------------------

    def test_search_returns_scored_playables(self):
        results = self.h.search(Signals(title="worms"))
        self.api.search_media.assert_called_once_with("worms", limit=10)
        self.assertTrue(results and all(isinstance(r, Release) for r in results))
        self.assertTrue(all(0.0 <= r.match_confidence <= 1.0 for r in results))
        # exact title outranks the partial match -> ranking is meaningful
        by_title = {r.work.title: r.match_confidence for r in results}
        self.assertGreater(by_title["Worms"], by_title["Food for the Worms"])
        self.assertTrue(all(r.uri.startswith("library://") for r in results))

    def test_search_swallows_backend_error(self):
        self.api.search_media.side_effect = RuntimeError("server exploded")
        self.assertEqual(self.h.search(Signals(title="worms")), [])

    def test_search_narrows_to_requested_medium(self):
        radio = self.h.search(Signals(title="worms", medium=MediaType.RADIO))
        self.assertTrue(radio)
        self.assertTrue(all(r.work.media_type == MediaType.RADIO for r in radio))


if __name__ == "__main__":
    unittest.main()
