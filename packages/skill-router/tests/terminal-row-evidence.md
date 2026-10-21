# Terminal evidence: the skill-router tool result row

Date: 2026-10-21. Pi 1.3.0, real interactive TUI under a PTY, no remote model.

## What was exercised

A direct call to `skill_router__upstream__seo_audit` in the interactive
transcript, the `ctrl+o` expansion of that row, and a live resize of the same
component from 120x40 to 60x24. The run used an offline scripted provider
(`skill-router-offline/scripted`) that issues exactly one tool call, so the row
appears deterministically instead of depending on a model's choice.

Setup: `PI_CODING_AGENT_DIR` pointing at a disposable agent directory holding one
installed collection and its materialized leaf, a disposable cwd, `PI_OFFLINE=1`,
a fixture extension that calls `skillRouter(pi)` and registers the scripted
provider, and `--tools read,skill_router__*`.

A `codemode`-exposure tool is callable from a script but never declarable
(`_isDeclarable` accepts only `direct` and `model-only`), so a direct call exists
only once something declares it. The fixture declares it with
`pi.setActiveTools([...pi.getActiveTools(), tool])` — the API `tool_search` uses
internally — because an allowlist match cannot. That is a test-only declaration;
the production path to a direct call is `tool_search` loading the tool.

## Observed

- At 120x40: `[skill-router] loaded · upstream/seo-audit · ctrl+o to expand`
- After `ctrl+o`: the row's detail line reveals
  `.../collections/upstream/leaves/seo-audit/SKILL.md`
- After the live resize to 60x24, the same component on screen:
  `[skill-router] loaded · upstream/seo-audit`
- 7 synchronized frames and 8102 raw bytes for the row check; 8 frames and 12710
  raw bytes with the expansion. No composed line exceeded 120 columns.

The screen was reconstructed from the PTY bytes with `pyte` (the parser this
repository's other terminal checks use), publishing only complete synchronized
frames (`\x1b[?2026l`), and the raw bytes were inspected alongside it. The raw
capture was scratch and is not retained here; the composed lines above, the
dimensions, the interaction order (row, then `ctrl+o`, then resize), and the
setup are the retained evidence.

## Scope

The row is passive: it owns no input handling, no focus, and no viewport, so key
ownership, navigation, and parent-return paths are not exercised here and nothing
about them is claimed. A direct call is also not the primary path — a codemode
script's call is nested and renders no transcript row — so this file covers the
row that a `tool_search`-loaded call produces.

## Reproduce

1. Install one local collection with the router harness into a disposable agent
   directory, so a gateway and its leaves are materialized.
2. Write a fixture extension that calls the package's `skillRouter` and registers
   a provider whose first scripted turn returns one tool call naming the skill
   tool, and whose `session_start` adds that name with `setActiveTools`.
3. Start `pi` in a PTY at 120x40 with `-e <fixture>`, `--model
   <fixture-provider>/scripted`, `--tools read,skill_router__*`, `PI_OFFLINE=1`,
   the disposable agent directory, and a disposable cwd.
4. Feed the bytes to a terminal-state parser, require the row, send `\x0f` for
   `ctrl+o` and require the detail, then resize the PTY to 60x24 with `SIGWINCH`
   and require the row's identity again.