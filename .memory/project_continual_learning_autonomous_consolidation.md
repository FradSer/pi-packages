---
name: continual-learning-autonomous-consolidation
description: Settled-task learning separates contextual memory from executable constraints and applies parent-validated updates
type: project
---

## Why

The consolidation workflow is intended to run without user prompts. A child Pi stream can contain oversized `message_update` telemetry that is not a plan; treating that telemetry as a fatal plan-format error prevents autonomous consolidation for no safety benefit.

## How to apply

- Memory, harness, and AGENTS.md phases apply only after their existing mechanical gates pass, but do not ask the user to accept individual operations.
- Auto-memory starts learning from completed user tasks. Memory and skill guidance provide pre-generation context; Harness checks tool calls, completed assistant text, and bounded file artifacts. Post-generation feedback cannot retract streamed text.
- New memories use an evidence-cited creation scope separate from selected existing files. User preferences stay private; credentials are rejected. Learned policies require actual user/tool quotes and executed positive/negative cases, and must not weaken user-owned constraints automatically.
- Ignore oversized non-plan JSONL telemetry while continuing to locate the final structured plan.
- Keep total stdout, line-count, actual plan-size, identity, evidence, anchor, budget, and atomic-write safeguards fail-closed.
- Real plan-bound violations or total-output exhaustion remain diagnostics and must not be silently applied.
