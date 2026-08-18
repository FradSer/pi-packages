---
"@fradser/pi-agent-teams": patch
"@fradser/pi-btw": patch
"@fradser/pi-memory": patch
"@fradser/pi-monitor": patch
"@fradser/pi-recap": patch
"@fradser/pi-utils": patch
"@fradser/pi-vision": patch
---

Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:

- Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
- The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
- Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
- Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
- monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.

Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.
