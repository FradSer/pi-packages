---
"@fradser/pi-kit": minor
"@fradser/pi-context": patch
---

Pi-kit owns the canonical minimal worker grant (`read`, `bash`, `grep`, `find`), and a minimal worker without a supplied allowlist now receives it instead of Pi's default active tool set.

**pi-kit**

- `minimalPiWorkerArgs()` had no default, so a package that wanted the canonical grant had to name its own tools. The new `MINIMAL_PI_WORKER_TOOLS` export names it, and `minimalPiWorkerArgs()` falls back to it.
- `runPiWorker({ minimal: true })` without `tools` disabled extension, skill, prompt-template, context-file, and theme discovery but left Pi's default active tools — `read`, `bash`, `edit`, and `write` — available, so a minimal worker could still write. It now receives exactly the canonical grant. `grep`, `find`, and `ls` were not part of that default set either.
- A supplied allowlist stays authoritative, including an explicit empty list, which still grants no tools and does not fall back to the default.
- An empty-string allowlist is a degenerate spelling of "no allowlist supplied": it now means the same thing in minimal and full mode instead of granting nothing in one and the default selection in the other. Only an empty array asks for no tools.
- `grep` and `find` come from Pi's built-in tools, so discovery costs no extra model turn per lookup with no extension or third-party search package added.

**@fradser/pi-context**

- The research child's grant was a package-local `RESEARCH_TOOLS = ["read", "bash"]`, and every file lookup cost a separate model turn. It now uses `MINIMAL_PI_WORKER_TOOLS` (`read`, `bash`, `grep`, `find`), which keeps the grant inspection-only in intent and single-sourced while cutting the turns a research question costs.
- The bundled worker prompt names the allowlisted tools and asks the child to prefer `grep` and `find` for locating files and matching lines.