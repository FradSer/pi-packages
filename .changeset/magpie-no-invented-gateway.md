---
"@fradser/pi-magpie": patch
---

Fix "installed and configured, but unusable": a saved key alone no longer implies `127.0.0.1`.

The provider resolved a credential holding only a key into `baseUrl: http://127.0.0.1:3425/v1`. Pi treats a resolved `baseUrl` as an override of the model's own address, so every request ignored the gateway `models.json` named and went to the local machine instead — the catalog listed models, `pi auth check` said `ready`, and turns failed. Adding `MAGPIE_BASE_URL` to the shell appeared to fix it only because the environment then supplied the address.

The resolved address is now omitted when the extension does not know one, leaving the model's own address in force. Seeding reads the credential `/login` saved, so a login works with no `models.json` and no environment variables, and a `models.json` gateway combines with a `/login` key because the key and the address resolve independently.
