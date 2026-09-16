# Repository Guidelines

## Project Structure

`packages/impeccable/` publishes `@fradser/pi-impeccable`, a design procedure and
taste library package for Pi. Package-root `index.ts` re-exports `src/index.ts`.
`src/index.ts` wires the `/impeccable` command menu, `impeccable_load` tool,
message renderer for `impeccable-procedure`, and `before_agent_start` intent router.
`src/resolver.ts` resolves procedures and taste references from `procedures/`
and `references/` into markdown guidance bundles. `src/catalog.ts` and
`src/catalog.json` manage capabilities, topic relationships, and reference
disclosures. `src/command-triggers.json` and `src/routing.ts` map freeform
requests and intent phrases (English and Chinese) to catalog capabilities.
`scripts/` houses live inspection and browser tooling (`live-server.mjs`,
`live-browser.js`, `live-inject.mjs`, `live-accept.mjs`, etc.) with bounded
HTTP request parsing in `scripts/live/http-body.mjs`. BDD contracts live in
`features/`; unit and integration tests live in `tests/`.

## Commands

Run from the repository root:

```bash
python3 -m pytest packages/impeccable/tests/ -q
node --import tsx/esm --test packages/impeccable/tests/loader.test.mjs
node --import tsx/esm --test packages/impeccable/tests/routing.test.mjs
pnpm --dir packages/impeccable pack --dry-run
```

## Style and Architecture

- **Stateless Guidance Loading**: `impeccable_load` loads design guidance
  without executing scripts or triggering extra turns. Loading guidance never
  authorizes autonomous edits, package installs, variant generation, or promotion;
  the agent works strictly within the user's explicit request.
- **Strict Bundle Byte Budget**: Resolved procedure bundles must not exceed 64 KiB
  (`MAX_BUNDLE_BYTES`). Oversized bundles fail hard without truncation; required
  closures must remain narrow and clean.
- **Progressive Disclosure**: Model capabilities disclose available reference
  links (`](impeccable:<referenceId>)`). Disclosed references are loaded via
  `impeccable_load` with `{ capability, reference }` only when their specific
  conditions apply (e.g. motion, components, color, typography, accessibility).
- **Bounded Request Limits**: The live server enforces a 1 MiB (`MAX_HTTP_BODY_BYTES`)
  body limit on incoming JSON requests in `scripts/live/http-body.mjs`, rejecting
  larger payloads with HTTP 413 to prevent memory exhaustion.
- **Marker and Source Hygiene**: Live variant previews use temporary
  `data-impeccable-*` attributes and comment markers (`impeccable-variants-start`,
  `impeccable-carbonize-start`). During accept or completion, all preview
  scaffolding and markers must be cleanly removed from user source code.

## Testing Guidelines

`features/impeccable.feature` and `features/http-body-limits.feature` specify
BDD scenarios. Python tests (`tests/test_*.py`) and Node test runner harnesses
(`tests/loader.test.mjs`, `tests/routing.test.mjs`) verify bundle size caps,
canonical link resolution, Chinese intent routing, live server HTTP body limits,
and clean unpack/pack manifests. Pack checks must include `index.ts`, `src`,
`procedures`, `references`, `scripts`, and license files.
