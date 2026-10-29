---
"@fradser/pi-magpie": minor
---

`/login magpie` now sets up the whole provider. It asks for the gateway address as well as the key, because magpie can run on this machine, in Docker, or on another host and the key alone cannot say which. Both answers are proved with one catalog request before anything is saved, so a wrong URL or key is reported at login instead of arriving later as a request timeout. The address is stored beside the key, so no environment variable is needed afterwards; a bare `host:port` gains its scheme and `/v1`, an address with a path is kept as typed, and `MAGPIE_BASE_URL` no longer overrides a saved gateway.

The README now leads with the screens of that flow, captured from a real Pi session — the gateway prompt, the key prompt naming the gateway it checked, the save confirmation, and the models it made selectable.
