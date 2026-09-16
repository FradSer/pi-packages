---
"pi-continual-learning": minor
---

Implement the flat Harness rules redesign: a single `rules` list with three selectors (`skill`, `bash`, `text`), stable rule `id`, and whole-rule nearest-layer override. Bash rules deliver a model-visible message on execution (omitted `action`), or gate the call with `confirm`/`block`; every matched message is collected and the call decision is order-independent. Invalid bash-scoped or ambiguous rules make Bash evaluation incomplete (fail closed) instead of silently executing, while clearly skill/text-scoped errors stay isolated.

Skill and text guidance is delivered as a durable `before_agent_start` message (retained on the branch, deduplicated against retained guidance, prefix-stable for caching), replacing the ephemeral `context`-hook approach. Text rules scan the model-visible retained conversation (history and tool results) at agent start; same-run mid-run tool-result triggering is a documented follow-up pending a verified Pi delivery seam. `/harness` authoring, status, and target initialization now use the `rules` format; existing user files and the automatic-consolidation subsystem keep working through the legacy read path during migration.
