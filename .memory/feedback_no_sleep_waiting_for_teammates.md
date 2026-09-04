---
name: no-sleep-waiting-for-teammates
description: Never use sleep or polling to wait for resident teammate completion; end the turn and rely on automatic report delivery
category: pitfall
type: feedback
---

## Why

Agent Teams automatically delivers a teammate's terminal report into the main session when the teammate completes. Running `sleep`, repeated greps, or status-request loops wastes tool calls, blocks useful work, and duplicates the coordination mechanism. This occurred during the continual-learning layer-alignment review, where repeated `sleep 8`/`sleep 10` calls were used while review teammates were still working.

## How to apply

After spawning or steering a teammate, continue independent work if any exists. If the next step depends entirely on the teammate, stop the turn without issuing a waiting command. The teammate report will resume the main session automatically. Do not poll its files, send repeated status requests, or use `sleep` as a synchronization primitive.

## Related

[[project_teammate_autonomous_and_tui]]
[[project_follow-up-queue]]
