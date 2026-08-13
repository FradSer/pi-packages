---
name: pi-kitty-csi-u-keys
description: pi negotiates the Kitty keyboard protocol (flags=7) — Esc is \x1b[27u, Shift+arrows are \x1b[1;2:1A/B; match keys with CSI-u-aware regexes
type: reference
---

pi-tui pushes `\x1b[>7u` (Kitty protocol flags 7 = disambiguate + report-events + alternate-keys) to supporting terminals (Ghostty, kitty, …). Under it:

- **Esc** = `\x1b[27u` (CSI-u), not bare `\x1b` (bare `\x1b` only in legacy terminals)
- **Shift+Up/Down** = `\x1b[1;2A` / `\x1b[1;2B` arrow form, with an `:1` press-event suffix under flag 2 → `\x1b[1;2:1A`; release events append `:3`
- **Plain ↑/↓** = `\x1b[A` / `\x1b[B` (or disambiguated `\x1b[1;1A`)
- **ctrl+p / ctrl+l** arrive as CSI-u `\x1b[112;5u` / `\x1b[108;5u`, not raw control bytes

**Why:**
Exact-string matching of `\x1b[1;2A` failed in Ghostty (which sends `\x1b[1;2:1A`), and Esc matching failed against `\x1b[27u` — the teammate panel's keys "did nothing" until the CSI-u forms were handled.

**How to apply:**
1. Match Esc with `data === "\x1b" || /^\x1b\[27(?:[:;\d]*)?u$/.test(data)`.
2. Match Shift+↑/↓ with `/^\x1b\[1;2(?::\d+)?A$|^\x1b\[a$/` (up) and `/^\x1b\[1;2(?::\d+)?B$|^\x1b\[b$/` (down) — covers arrow form, event suffix, and legacy DEC `\x1b[a`/`\x1b[b`.
3. Filter key releases with `isKeyRelease(data)` from `@earendil-works/pi-tui` when listening on raw input.
4. Inside a `ctx.ui.custom` component pi already parses CSI-u and filters releases — only the page's own keys need handling.
5. Reference: pi-tui `dist/keys.js` (`parseKittySequence`, `LEGACY_SEQUENCE_KEY_IDS`).

**Related:** [[no-global-input-interception]] [[pi-custom-component-rendering]]
