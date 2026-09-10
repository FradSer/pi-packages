---
"pi-continual-learning": patch
---

Classify consolidation planner model errors (quota 429, model cooldown) as labeled model failures instead of generic "missing schema-valid consolidation plan" rejections, and skip the fresh-planner retry that inherits the same failing model. Label dreaming-budget terminations as timeouts instead of raw exit codes, carry the previous rejection reason into the fresh planner's task header, emit validator errors once per category without duplicated prefixes, clip rejection notifications from the head, and document that grounding observations must cite existing files (skill directories via their SKILL.md).
