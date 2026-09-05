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
pnpm exec tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/vision pack --dry-run
```

## Style and Architecture

Keep image extraction, model requests, configuration,
and Pi event wiring in their existing modules. Authenticate and complete
requests through Pi's model registry; pass the Pi abort signal through. Only
bridge images for text-only active models. Preserve the user's visible prompt
and original attachments; add successful analysis only to transient provider
context or enriched tool results. Persist settings through Pi's agent directory
(`vision.json`), with documented environment variables as fallback.

## Testing Guidelines

`features/image-bridge.feature`, `tests/test_vision_package.py`, and
`tests/vision_input_harness.ts` cover success, failure, multimodal bypass, path
extraction, prompt-scoped caching, and tool-result cases. Use generated test
images and an isolated `PI_CODING_AGENT_DIR`, not personal attachments or
credentials. Keep README configuration examples aligned with persisted-value
precedence over environment fallbacks.
