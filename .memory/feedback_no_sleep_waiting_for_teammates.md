---
name: no-sleep-waiting-for-teammates
description: Never use sleep, polling, status requests, or agent inspection to wait for resident teammate completion; end the turn and rely on automatic report delivery
category: pitfall
type: feedback
---

## Why

Agent Teams automatically delivers a teammate's terminal report into the main session when the teammate completes. Any synchronous waiting mechanism wastes tool calls, blocks useful work, and duplicates the coordination mechanism. Observed anti-patterns:

- `sleep 8` / `sleep 10` calls used while review teammates were still working (continual-learning layer-alignment review).
- `agent({name})` without a prompt (returning `inspected`) used to check whether a teammate had finished. The feature contract explicitly forbids extending the turn with "sleep, polling, task_list, or status requests"; inspection-as-polling is a status request in a different tool signature.

## How to apply

After spawning or steering a teammate, continue independent work if any exists. If the next step depends entirely on the teammate, stop the turn without issuing a waiting command. The teammate report will resume the main session automatically.

Do not:
- Use `sleep` as a synchronization primitive.
- Poll teammate files or use `agent({name})` inspection to check completion.
- Send repeated status requests or unsolicited steers asking for progress.

Legitimate uses of `agent({name})` inspection (without prompt) include: looking up precise `work` and route handles when multiple Work Sessions exist, responding to an abnormal diagnostic that requires state inspection, or user-requested status checks. The disqualifying signal is using it to wait for a report that will arrive automatically.

## Related

[[project_teammate_autonomous_and_tui]]
[[project_follow-up-queue]]
[[project_agent_leader_priority]]
