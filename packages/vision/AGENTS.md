# Repository Guidelines

## Project Structure

`packages/vision/` publishes `@fradser/pi-vision`, a transparent image-to-text
bridge. `index.ts` is the package entry point; implementation is split under
`src/`: `index.ts` owns Pi hooks and `/vision`, `bridge.ts` calls the configured
vision model, `config.ts` persists settings, and `input-images.ts` extracts
readable image paths. BDD contracts are in `features/`; executable tests and
the TypeScript harness are in `tests/`.

## Commands

Run from the repository root:

```bash
python3 -m pytest packages/vision/tests/ -q
npx tsc --noEmit --strict --skipLibCheck --target ES2022 \
  --module ESNext --moduleResolution bundler --types "" packages/vision/src/*.ts
pnpm --dir packages/vision pack --dry-run
```

`pnpm test` runs all package tests.

## Style and Architecture

Use ESM TypeScript and keep image extraction, model requests, configuration,
and Pi event wiring in their existing modules. Authenticate and complete
requests through Pi's model registry; pass the Pi abort signal through. Only
bridge images for text-only active models. Preserve the user's visible prompt
and original attachments; add successful analysis only to transient provider
context or enriched tool results. Persist settings through Pi's agent directory
(`vision.json`), with documented environment variables as fallback.

## Testing and Releases

Update `features/image-bridge.feature` before behavior changes, then extend
`tests/` and the harness for success, failure, multimodal bypass, path
extraction, caching, and tool-result cases. Add a Changeset for published
behavior or manifest changes and use Conventional Commit scopes such as
`feat(packages):`. Keep README configuration and package `files` entries aligned
with shipped source.
