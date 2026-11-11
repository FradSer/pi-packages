---
"@fradser/pi-kit": patch
"@fradser/pi-subagents": patch
"@fradser/pi-agent-teams": patch
"@fradser/pi-context": patch
"@fradser/pi-plan-mode": patch
---

Unify Pi's hidden-thinking setting across above-editor agent activity rows. `pi-kit` now owns the label (`Thinking...`), the per-refresh `hideThinkingBlock` reader, the tool/reasoning/answer display policy, and an additive `activitySource` on worker progress snapshots. Subagents, agent-teams, context and plan-mode use that one contract, so a reader who hid thinking blocks sees Pi's label instead of streamed reasoning on every agent row; tool names and answers still take precedence, and visible thinking is unchanged.
