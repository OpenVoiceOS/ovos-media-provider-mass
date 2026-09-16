"""OVOS MediaProvider plugin for Music Assistant.

Replaces the catalog/search half of the deprecated OCP skill
``ovos-skill-music-assistant``. Instead of answering ``ovos.common_play.query``
over the bus, this provider is loaded in-process by the OCP pipeline and its
:meth:`search` is called directly. Any request it cannot satisfy (no query, no
server configured, the server offline) yields an empty list.

All Music Assistant access is delegated to the ``py-music-assistant`` client and
its mediavocab bridge (``search_to_releases``), which yields
``mediavocab.Release`` objects. Each ``Release.uri`` is a
``library://<type>/<id>`` identifier that the companion
``ovos-media-plugin-mass`` audio backend resolves and plays.
"""
from typing import ClassVar, List, Optional, Set

from ovos_utils.log import LOG
from ovos_utils.parse import fuzzy_match

from mediavocab import MediaType, Release, Signals
from ovos_plugin_manager.templates.media_provider import MediaProvider

from py_music_assistant import (
    SimpleHTTPMusicAssistantClient,
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

    Serves the audio library types Music Assistant indexes — ``MUSIC``,
    ``RADIO``, ``PODCAST``, ``AUDIOBOOK`` — all consumed as audio streams.
    """

    name: ClassVar[str] = "music_assistant"

    #: library media types this provider can satisfy; a request for any other
    #: medium narrows to nothing and ``search`` returns ``[]``.
    SERVED_MEDIA: ClassVar[Set[MediaType]] = {
        MediaType.MUSIC,
        MediaType.RADIO,
        MediaType.PODCAST,
        MediaType.AUDIOBOOK,
    }

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.url: str = (self.config.get("url") or "").strip()
        self.token: Optional[str] = self.config.get("token")
        self.max_results: int = int(self.config.get("max_results", 10))
        self._api: Optional[SimpleHTTPMusicAssistantClient] = None

    @property
    def api(self) -> Optional[SimpleHTTPMusicAssistantClient]:
        """Lazily-built client. Returns ``None`` when no server url is set."""
        if not self.url:
            return None
        if self._api is None:
            self._api = SimpleHTTPMusicAssistantClient(self.url, token=self.token)
        return self._api

    def search(self, signals: Signals, lang: str = "en-us", *,
               supported_playback_types: Optional[Set[str]] = None,
               blocked_genres: Optional[Set[str]] = None,
               region: Optional[str] = None,
               session_id: Optional[str] = None) -> List[Release]:
        """Search Music Assistant for ``signals.title`` and return scored Releases.

        When ``signals.medium`` names a specific type this provider serves, the
        results are narrowed to that type; otherwise all playable results are
        returned. Each result's ``match_confidence`` is set by
        :func:`score_release`. Returns ``[]`` when there is no query, no server
        configured, or the server is unreachable.
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
        narrow = medium in self.SERVED_MEDIA  # a specific type we serve was requested

        out: List[Release] = []
        for rel in search_to_releases(res):
            if narrow and rel.work.media_type != medium:
                continue
            rel.match_confidence = score_release(rel, signals)
            out.append(rel)
        return out
