---
"pi-skill-router": patch
---

Expose only one namespace-derived gateway skill for each collection, keep selected sub-skills internal with their upstream names, and route matching requests directly to their internal files. Collection installation now ignores malformed and test-fixture skills, reports interactive progress, and derives a stable `owner-repo` internal id for GitHub collections.
