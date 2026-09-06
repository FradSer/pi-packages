---
"pi-continual-learning": patch
---

Classify consolidation planner model errors (quota 429, model cooldown) as labeled model failures instead of generic "missing schema-valid consolidation plan" rejections, and skip the fresh-planner retry that inherits the same failing model.
