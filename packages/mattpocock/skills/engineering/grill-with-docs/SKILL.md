---
name: grill-with-docs
description: Runs a relentless interview that sharpens a plan or design and creates docs (ADRs and glossary) along the way. Use when the user wants to stress-test a plan or design, or produce decision records.
disable-model-invocation: true
---

Run a `/skill:grilling` session, using the `/skill:domain-modeling` skill.

## CRITICAL: Grill with the docs skills loaded

Run the `/skill:grilling` session with the `/skill:domain-modeling` skill active. Every sharpened term and locked decision lands in `CONTEXT.md` or an ADR as it crystallises — the paper trail is what distinguishes this skill from `/skill:grill-me`. Interview questions go through the ask the user, one per call, as `/skill:grilling` dictates.
