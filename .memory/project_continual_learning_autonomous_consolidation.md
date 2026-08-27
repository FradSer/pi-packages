---
name: continual-learning-autonomous-consolidation
description: Consolidation applies validated memory, harness, and AGENTS.md updates autonomously; oversized non-plan telemetry is ignored
 type: project
---

## Why

The consolidation workflow is intended to run without user prompts. A child Pi stream can contain oversized `message_update` telemetry that is not a plan; treating that telemetry as a fatal plan-format error prevents autonomous consolidation for no safety benefit.

## How to apply

- Memory, harness, and AGENTS.md phases apply only after their existing mechanical gates pass, but do not ask the user to accept individual operations.
- Ignore oversized non-plan JSONL telemetry while continuing to locate the final structured plan.
- Keep total stdout, line-count, actual plan-size, identity, evidence, anchor, budget, and atomic-write safeguards fail-closed.
- Real plan-bound violations or total-output exhaustion remain diagnostics and must not be silently applied.
