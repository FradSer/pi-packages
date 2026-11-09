---
"pi-continual-learning": patch
---

Use the shared Memory filename guard for the consolidation selected scope. A real `~/Documents/Home Lab` plan selected `openwrt-upboard-1010101-25.12.md` (and other dotted version-style names such as `88.1-dual-wan-loadbalance-research.md`) and failed with `Consolidation plan selected[1] is not a canonical memory filename`, even though the corpus enumerator, `isMemoryFilename` and the structured validator all accept those names. `inject-memory.ts` kept a private stricter regex in two places: `normalizeSelectedScope` rejected the plan, and `parentSelectedScope` silently dropped dotted names from the parent-derived scope. Both now call `isMemoryFilename`, so the three surfaces agree; leading/consecutive/trailing dots, repeated `.md` segments, path components, `MEMORY.md` and duplicate names stay rejected. No gate or write path changes.
