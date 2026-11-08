---
"pi-continual-learning": patch
---

Fix two real-project learning failures. The incremental Memory validator now derives the same parent-owned classifications as the learning dossier: a selected file with no public mirror is private even when the private MEMORY.md row lacks a `(harness only)` marker. This removes the "Operation classification disagrees with parent-derived inventory" rejection in non-Git projects, along with the follow-on structural-repair rejection. Dotted version-style Memory filenames such as `88.1-dual-wan-loadbalance-research.md` are now accepted by both the TypeScript filename guard and the Python artifact validator; leading dots, consecutive dots, path components and repeated `.md` segments stay rejected.
