# 03 — Align memory consolidation ownership

**What to build:** Memory consolidation reads the resolved three-layer surface but atomically applies learned changes only to project-personal memory, using the existing validation and receipt guarantees.

**Blocked by:** 02 — Add three-layer memory resolution.

**Status:** ready-for-agent

- [ ] Shared memory bytes are unchanged by consolidation.
- [ ] Rewrites, deletes, extracted memories, and indexes target project personal.
- [ ] Snapshot hashes and receipts bind all inputs and the personal output.
- [ ] Rollback and shutdown safety remain intact.
