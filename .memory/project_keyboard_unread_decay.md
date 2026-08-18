---
name: keyboard-unread-decay
description: @fradser/pi-keyboard unread (green) state was held purely in memory and never time-decayed, so a session left unread for a long time kept the green light on forever — fixed by stamping a user-activity timestamp and decaying stale unread to idle
type: project
---

## Why

`packages/keyboard` reflects Pi's global state on a VIA/QMK keyboard via a `KeyboardStateMachine`. The "unread chat" green state is set on `onAgentSettled`. Two defects made green "stick" after the user left unread messages unhandled for a long time:

1. **Self in-memory unread is never stale-skipped.** `evaluateGlobalLightingState` guards OTHER sessions' on-disk records with a 5-minute staleness window (`maxStaleAgeMs`, also prunes dead PIDs), but the self session always injects its in-memory `hasUnreadChat` fresh — so once set, green persists beyond the staleness window until a keypress lands in that exact session.
2. **Unread is only cleared by a keypress** gated on `sm.isUnread()` in `onTerminalInput`/`rawStdin` (index.ts). A user who reads in another tab, or whose session just sits idle, never clears the flag.

## How to apply

- `KeyboardStateMachine` now stamps `lastUserActivityAt = this.now()` on `onAgentSettled` (when unread is set) and on `onUserActivated`/`onUserInput`/`onSessionStart`/`onAgentStart`.
- `buildSelfRecord` decays `hasUnreadChat` → false when `now() - lastUserActivityAt > STALE_UNREAD_MS` (5 min), so the next `syncAndEvaluate`/`writeSessionGlowState` emits an idle record instead of a green one — to the hardware and to every other session reading the registry.
- A `now: () => number` constructor arg (default `Date.now`) is the test seam; pass a fake clock in tests (`test_stale_unread_decays_to_idle_without_user_activity`, `test_stale_unread_cleared_on_user_activation`).
- BDD: `features/keyboard.feature` has the "Long-ago unread message decays" scenario.
- The physical keyboard holds the last-applied state, so if a session truly goes silent the light stays green until the first event re-evaluates — that is expected; the decay fixes the stuck-when-returning/re-evaluating case.

## Related

[[project_pi_package_conventions]] [[project_recap_persistence_design]]
