---
"@fradser/pi-context": patch
"@fradser/pi-kit": patch
---

Keep context research as a stateless one-shot worker with a package-local typed builder that uses Markdown only as a reference protocol, builds a concrete prompt from the current request and working directory, and retries an empty successful answer exactly once. The transcript renders `[context] research started · <research query>` on start, a toolPendingBg `[context] researching` band while the child streams progress, and a compact expandable toolSuccessBg `[context] researched · <research query>` band on completion whose details wrap instead of truncating, with the expand hint resolved from the app.tools.expand keybinding. Remove the obsolete shared package-agent prompt helper from pi-kit.
