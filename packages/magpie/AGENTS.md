# Magpie Package Guidelines

`packages/magpie/` publishes `@fradser/pi-magpie`. The extension registers the
complete live model and routing-group catalog from a running Magpie gateway
into Pi's model picker. Package entry `index.ts` re-exports `extensions/index.ts`.
Implementation is in `extensions/`: `provider.ts` wires the OpenAI-compatible
streaming provider, `catalog.ts` fetches and translates `/v1/models` into Pi
model structures, and `seed.ts` loads pre-session cached catalogs. Tests live
in `tests/`.

## Commands

Run focused tests from the repository root:

```bash
python3 -m pytest packages/magpie/tests/ -q
pnpm --dir packages/magpie pack --dry-run
```

## Structure and Invariants

- **Address Precedence**:
  1. Saved gateway URL from `/login magpie` in `auth.json`
  2. `baseUrl` configured under `providers.magpie` in `models.json`
  3. `MAGPIE_BASE_URL` environment variable
  4. Default: `http://127.0.0.1:3425/v1`
  Never invent `127.0.0.1` when `models.json` or `/login` provided an address.
  Key and gateway URL resolve independently.
- **Catalog Lifecycle**:
  - The catalog is requested at session start over the network at most once every
    5 minutes per process.
  - Successful refreshes are cached by Pi, ensuring offline startup retains the
    last known model list.
  - Failures, non-2xx responses, or empty responses preserve the existing list.
  - `MAGPIE_PI_MODELS` filters exposed model IDs by glob (e.g., `group/*`).
- **Thinking Support**: Thinking levels match the efforts reported per model by
  magpie; `off` is not supported when the gateway provides no per-request toggle.

## Task References

- Read @README.md for `/login` interaction flow and gateway configuration examples.
- For promotional video source and assets, see `promo-x/AGENTS.md`.
