# @fradser/pi-magpie

## 0.4.0

### Minor Changes

- 4d20b94: `/login magpie` now sets up the whole provider. It asks for the gateway address as well as the key, because magpie can run on this machine, in Docker, or on another host and the key alone cannot say which. Both answers are proved with one catalog request before anything is saved, so a wrong URL or key is reported at login instead of arriving later as a request timeout. The address is stored beside the key, so no environment variable is needed afterwards; a bare `host:port` gains its scheme and `/v1`, an address with a path is kept as typed, and `MAGPIE_BASE_URL` no longer overrides a saved gateway.
  
  The README now leads with the screens of that flow, captured from a real Pi session — the gateway prompt, the key prompt naming the gateway it checked, the save confirmation, and the models it made selectable.

### Patch Changes

- 275547a: Fix "installed and configured, but unusable": a saved key alone no longer implies `127.0.0.1`.
  
  The provider resolved a credential holding only a key into `baseUrl: http://127.0.0.1:3425/v1`. Pi treats a resolved `baseUrl` as an override of the model's own address, so every request ignored the gateway `models.json` named and went to the local machine instead — the catalog listed models, `pi auth check` said `ready`, and turns failed. Adding `MAGPIE_BASE_URL` to the shell appeared to fix it only because the environment then supplied the address.
  
  The resolved address is now omitted when the extension does not know one, leaving the model's own address in force. Seeding reads the credential `/login` saved, so a login works with no `models.json` and no environment variables, and a `models.json` gateway combines with a `/login` key because the key and the address resolve independently.
