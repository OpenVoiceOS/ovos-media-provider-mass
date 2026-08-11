# Configuration

Settings live under the top-level `media_providers` key of `mycroft.conf`, keyed
by this provider's entry-point name `music_assistant`. Any keys are passed
through to the provider's `config` dict.

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

| Key | Type | Default | Meaning |
|---|---|---|---|
| `url` | str | *(none)* | Music Assistant server base URL. **Required.** Without it, the provider reports itself unavailable and is skipped at load. |
| `max_results` | int | `10` | Max results requested from the server per search. |
| `enabled` | bool | `true` | Set `false` to disable the provider without uninstalling it (handled by the pipeline loader). |

## Pairing with the playback backend

This provider only finds media. Playback of the `library://…` uris it returns is
done by [`ovos-media-plugin-mass`](https://github.com/OpenVoiceOS/ovos-media-plugin-mass),
configured under the `media` block with the same server `url` and a player
`identifier`. Run `ovos-mass-autoconfigure` (shipped by that plugin) to populate
the backend config from your server's players.

---
[← Overview](index.md) · [Home](../README.md)
