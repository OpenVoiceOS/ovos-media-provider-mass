# ovos-media-provider-mass

OVOS **MediaProvider** plugin for [Music Assistant](https://www.music-assistant.io/).

It is the catalog/search half of the Music Assistant integration for the
`ovos-media` stack: given a parsed media request it searches a Music Assistant
server and returns ranked, playable `mediavocab.Release` objects. Playback of the
returned `library://…` uris is handled by the companion
[`ovos-media-plugin-mass`](https://github.com/OpenVoiceOS/ovos-media-plugin-mass)
audio backend.

It supersedes the catalog/search half of the legacy OCP skill
[`ovos-skill-music-assistant`](https://github.com/OpenVoiceOS/ovos-skill-music-assistant).

## Routing

| Axis | Value |
|---|---|
| `media` | `MUSIC`, `RADIO`, `PODCAST`, `AUDIOBOOK` |
| `playback_type` | `AUDIO` |
| `genre_filter` | *(none)* |

## Install

```bash
pip install ovos-media-provider-mass
```

> **Note (ovos-media sprint):** the `opm.media.provider` plugin type lives in
> `ovos-plugin-manager`'s `feat/media-provider-plugin-type` branch and is not on
> PyPI yet, so until it ships you need:
> ```bash
> pip install git+https://github.com/OpenVoiceOS/ovos-plugin-manager@feat/media-provider-plugin-type
> ```
> CI installs it the same way; `opm-check` is wired back once that support is released.

## Configure

Per-provider settings live under `media_providers` in `mycroft.conf`, keyed by
the provider's entry-point name:

```json
{
  "media_providers": {
    "music_assistant": {
      "url": "http://192.168.1.100:8095",
      "max_results": 10
    }
  }
}
```

`url` is required (the provider reports itself unavailable without it). Set
`"enabled": false` to disable without uninstalling.

## Related projects

- [py-music-assistant](https://github.com/TigreGotico/py-music-assistant) — shared HTTP client + mediavocab bridge (this provider's transport layer)
- [ovos-media-plugin-mass](https://github.com/OpenVoiceOS/ovos-media-plugin-mass) — Music Assistant playback backend (plays the `library://` uris this provider returns)
- [ovos-skill-music-assistant](https://github.com/OpenVoiceOS/ovos-skill-music-assistant) — the legacy OCP search skill this provider supersedes

## Docs

- [docs/index.md](docs/index.md) — overview & how it fits the ovos-media stack
- [docs/configuration.md](docs/configuration.md) — configuration reference

## Tests

```bash
pip install -e .[test]
pytest test/                                            # unit + end2end, network-free
MASS_SERVER_URL=http://<host>:8095 pytest test/live/    # opt-in, real server
```

The end-to-end tests ([test/end2end/](test/end2end/)) discover the provider
through its real `opm.media.provider` entry-point and drive the full
discover → `serves()` gate → `search_safe` path the OCP pipeline takes, with the
Music Assistant client mocked.

## License

Apache-2.0
