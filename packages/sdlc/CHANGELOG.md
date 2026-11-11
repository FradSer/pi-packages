# pi-sdlc

## 0.2.0

### Minor Changes

- 4d20b94: Add the full artifact-driven SDLC workflow with faithful intent capture, a concise
  current handoff, digest-bound stage checks, independent approval and evaluation
  adapters, review, gated release with rollback, task archives and metric-to-intent
  feedback. Include native Pi print/RPC and packed full-pipeline acceptance.

### Patch Changes

- 97e9add: Document the workspace's bun-only commands instead of the earlier package manager. Contributor guides, README verification blocks, BDD wording and shipped command examples now use `bun run typecheck`, `bun run check:install`, `bun pm pack` and `bun test`. Test fixtures and opt-in Docker acceptance harnesses invoke bun directly. No runtime behavior changes.
- baf2696: Record installed SDLC method provenance, review-policy digest and external review/approval references, and metadata-only global lifecycle events without creating a second methods directory, copying per-task REVIEW.md files, or mirroring chat transcripts.
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [a3ee3e3]
- Updated dependencies [2bba220]
- Updated dependencies [a0923d8]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [842b92e]
- Updated dependencies [2116b41]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-kit@0.6.0
