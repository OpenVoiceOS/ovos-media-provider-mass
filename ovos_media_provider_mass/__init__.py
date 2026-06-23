"""OVOS MediaProvider plugin for Music Assistant.

Replaces the catalog/search half of the deprecated OCP skill
``ovos-skill-music-assistant``. Instead of answering ``ovos.common_play.query``
over the bus, this provider is loaded in-process by the OCP pipeline, gated by
the three-axis routing test, and its :meth:`search` is called directly.

All Music Assistant access is delegated to the ``py-music-assistant`` client and
its mediavocab bridge (``search_to_releases`` / ``recently_played_to_releases``),
which yield ``mediavocab.Release`` objects. Each ``Release.uri`` is a
``library://<type>/<id>`` identifier that the companion
``ovos-media-plugin-mass`` audio backend resolves and plays.
"""
from typing import ClassVar, List, Optional, Set

from ovos_utils.log import LOG
from ovos_utils.parse import fuzzy_match

from mediavocab import MediaType, Release, Signals
from mediavocab.taxonomy import PlaybackType
from ovos_plugin_manager.templates.media_provider import MediaProvider

from py_music_assistant import (
    SimpleHTTPMusicAssistantClient,
    recently_played_to_releases,
    search_to_releases,
)

from ovos_media_provider_mass.version import __version__  # noqa: F401


def score_release(release: Release, signals: Signals) -> float:
    """Score a Release against the parsed request, in ``0.0``–``1.0``.

    Title similarity (``fuzzy_match``) is the base; a small bonus is added when
    the requested artist appears in the result and when the item is a Music
    Assistant favourite. The OCP pipeline ranks across providers, so only the
    relative order within this provider's results matters.
    """
    query = (signals.title or "").strip().lower()
    title = (release.work.title or "").lower()
    score = fuzzy_match(title, query) if query else 0.5

    artist = (release.work.extra.get("artist") or "").lower()
    want_artist = (signals.artist or "").strip().lower()
    if artist and (want_artist or query):
        if (want_artist and want_artist in artist) or (query and artist in query):
            score = min(1.0, score + 0.1)
    if release.work.extra.get("favorite"):
        score = min(1.0, score + 0.1)
    return round(score, 3)


class MAssMediaProvider(MediaProvider):
    """Search a Music Assistant server and return ``mediavocab.Release`` playables.

    Routing (three-axis gate):

    * ``media`` — ``MUSIC``, ``RADIO``, ``PODCAST``, ``AUDIOBOOK`` (the library
      types Music Assistant indexes).
    * ``playback_type`` — ``AUDIO`` only (everything Music Assistant serves is
      consumed as an audio stream).
    * ``genre_filter`` — empty (no genre gate).
    """

    name: ClassVar[str] = "music_assistant"

    media: ClassVar[Set[MediaType]] = {
        MediaType.MUSIC,
        MediaType.RADIO,
        MediaType.PODCAST,
        MediaType.AUDIOBOOK,
    }

    playback_type: ClassVar[Set[PlaybackType]] = {PlaybackType.AUDIO}

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.url: str = (self.config.get("url") or "").strip()
        self.max_results: int = int(self.config.get("max_results", 10))
        self._api: Optional[SimpleHTTPMusicAssistantClient] = None

    @property
    def api(self) -> Optional[SimpleHTTPMusicAssistantClient]:
        """Lazily-built client. Returns ``None`` when no server url is set."""
        if not self.url:
            return None
        if self._api is None:
            self._api = SimpleHTTPMusicAssistantClient(self.url)
        return self._api

    def is_available(self) -> bool:
        """True when a server url is configured and the server answers.

        A cheap ``players/all`` round-trip doubles as a reachability probe so an
        unconfigured or offline server is skipped at load instead of failing
        every search.
        """
        if self.api is None:
            LOG.debug("Music Assistant provider has no 'url' configured")
            return False
        try:
            self.api.get_players()
            return True
        except Exception:
            LOG.exception(f"Music Assistant server not reachable at {self.url}")
            return False

    def search(self, signals: Signals, lang: str = "en-us") -> List[Release]:
        """Search Music Assistant for ``signals.title`` and return scored Releases.

        When ``signals.medium`` names a specific type this provider serves, the
        results are narrowed to that type; otherwise all playable results are
        returned. Each result's ``match_confidence`` is set by
        :func:`score_release`.
        """
        query = (signals.title or "").strip()
        if not query or self.api is None:
            return []

        try:
            res = self.api.search_media(query, limit=self.max_results)
        except Exception:
            LOG.exception(f"Music Assistant search failed for query: {query!r}")
            return []

        medium = signals.medium
        narrow = medium in self.media  # a specific type we serve was requested

        out: List[Release] = []
        for rel in search_to_releases(res):
            if narrow and rel.work.media_type != medium:
                continue
            rel.match_confidence = score_release(rel, signals)
            out.append(rel)
        return out

    def featured_media(self, lang: str = "en-us") -> List[Release]:
        """Recently-played items from the server as curated/home content."""
        if self.api is None:
            return []
        try:
            return recently_played_to_releases(self.api.recently_played())
        except Exception:
            LOG.exception("Music Assistant recently-played fetch failed")
            return []
