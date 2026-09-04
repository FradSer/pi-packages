---
name: project-teammate-spawn-tool-grant
description: Spawn teammates with explicit tools and verify the grant; queued-message loss was a status-truth bug (fixed 847cd86); use one-shot pi --print agents as fallback when residents hang.
type: project
---

# Teammate spawn tooling and one-shot review fallback

## Why

During a PR review session (2026-08-24), three of six resident teammates woke without
bash/read because their inline definitions omitted `tools` — each burned turns before
reporting incapability. Two others hung silently on provider requests (zero tokens,
single stalled connection to cli-proxy). PR #18 (merged) made the grant visible at
spawn time and guidance now requires explicit read/bash for file work.

## How to apply

- Inline teammate definitions MUST include `"tools": ["read", "bash"]` whenever the
  kickoff reads files or runs commands; check the spawn result line `(tools: ...)`
  immediately after spawning — capability-only grants are visible there now.
- If a resident teammate ignores a queued message (wakes, reports "board empty, standing by") or hangs silently, shut it down and fall back to a ONE-SHOT independent agent:
  `pi --print --no-session --tools read,bash "<skeptical-review-prompt>"` wrapped in a monitor with events embedded in the sentinel JSON. It avoids the RPC layer and worked every time residents failed.
- ROOT CAUSE of ignored messages was FIXED in 847cd86 (PR #19): prompt-less spawns run a kickoff turn immediately but were marked idle at birth, so messages queued instead of steered and were lost inside the running turn. Status now flows starting→working→idle from stream truth only. On older runtimes, resend once (steer path) before giving up.
- One-shot reviewer prompts must say: ignore the local working tree (parallel sessions
  keep unrelated WIP in shared checkouts) and fetch ONLY `gh pr diff <n> --repo <owner>/<repo>`.
- Never run test/build commands inside `$? | tail` pipes without `set -o pipefail`; a
  masked pytest failure once slipped into a commit.
