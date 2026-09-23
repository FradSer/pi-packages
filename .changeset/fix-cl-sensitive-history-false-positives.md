---
"pi-continual-learning": patch
---

Stop learning history from refusing ordinary learned text. Credential detection now requires an assigned value long enough to be a credential or a concrete provider key format, so wiki links and names such as `skills-host-agnostic`, workflow permission names such as `id-token: write`, and prose such as `Auth is delegated` no longer fail the whole pipeline with `Learning history refuses sensitive material`. Real assignments, provider keys, private keys and bearer tokens are still refused.