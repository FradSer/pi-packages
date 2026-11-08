---
"@fradser/pi-subagents": patch
---

Keep runtime bookkeeping out of expanded subagent control rows. An `agent_start`, `agent_input` or `agent_stop` row now expands to the authored input plus substantive outcome facts (model, tools, role description, evidence, preview, error); exact session/input handles, observed state, pending intent, queued count and next actor remain in the model-facing structured details instead of the transcript. `agent_list` keeps its expanded handles and live facts because looking up exact incarnations is that tool's purpose. Child-to-parent intermediate messages and cancelled-input notices likewise show their body/reason without session, input or sequence identifiers.
