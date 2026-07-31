# ovos-media-provider-mass

A [MediaProvider](https://github.com/OpenVoiceOS/ovos-media/blob/dev/docs/media-providers.md)
plugin that turns a Music Assistant server into a catalog the `ovos-media` stack
can search.

## Where it sits

```
utterance ─▶ OCP pipeline ─▶ provider.search(signals) ─▶ list[Release]
                                     │                         │ uri = library://track/9903
                                     │                         ▼
                              (this plugin)            ovos-media daemon picks a backend
                                                                │
                                                                ▼
                                              ovos-media-plugin-mass.load_track(uri) ─▶ play
```

The provider is loaded **in-process** by the OCP pipeline (no bus round-trip),
gated by its three-axis routing, and its `search()` is called directly. It
returns `mediavocab.Release` objects. The daemon hands the winning uri to the
`ovos-media-plugin-mass` audio backend, which resolves and plays it.

## How it works

All Music Assistant access is delegated to the
[`py-music-assistant`](https://github.com/TigreGotico/py-music-assistant) client
and its mediavocab bridge:

1. `search(signals)` calls `SimpleHTTPMusicAssistantClient.search_media(signals.title)`.
2. `search_to_releases(...)` maps the response buckets to `Release` objects.
3. When `signals.medium` names a specific served type (`MUSIC`/`RADIO`/
   `PODCAST`/`AUDIOBOOK`), results are narrowed to it. Otherwise, all are returned.
4. Each result's `match_confidence` is scored against the request
   (title similarity + favourite/artist bonuses).

`featured_media()` surfaces the server's recently-played items for the browse
screen. `is_available()` requires a configured `url` and a reachable server.

## Relationship to the other Music Assistant repos

| Repo | Role |
|---|---|
| **ovos-media-provider-mass** (this) | catalog/search (`opm.media.provider`) |
| [ovos-media-plugin-mass](https://github.com/OpenVoiceOS/ovos-media-plugin-mass) | playback backend (`opm.media.audio`) |
| [ovos-skill-music-assistant](https://github.com/OpenVoiceOS/ovos-skill-music-assistant) | legacy OCP search skill (superseded by this provider) |
| [py-music-assistant](https://github.com/TigreGotico/py-music-assistant) | shared HTTP client + mediavocab bridge |

See [configuration.md](configuration.md) for settings.
