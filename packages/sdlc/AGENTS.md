# SDLC package

`index.ts` loads the native Pi lifecycle adapter in `src/index.ts`.
`src/records.ts` owns checked Markdown writes and a single latest handoff checkpoint.
The package bundles `references/workflow.md` and both templates; no external
dotcodex checkout is needed at runtime.

Run `uv run --with pytest python -m pytest packages/sdlc/tests -q`,
`pnpm typecheck`, and `pnpm --dir packages/sdlc pack --dry-run` from the repository.
`tests/live_sdlc.py` uses real Pi print and RPC with a deterministic local provider.
Keep this evidence separate from real-model instruction-following quality.

Do not record custom extension messages as user intent. Use `agent_settled`, not
`agent_end`, as the final lifecycle boundary. A stopped turn is not task completion.
The model must read the handoff before work and refresh it before finishing or
pausing. Keep source requests in INTENT.md and only current progress in HANDOFF.md.

Use pi-kit for exclusive JSON lock publication and notifications. It has no checked
Markdown writer; that package-specific gap is handled by `src/records.ts`.
Never steal locks, follow linked documents, overwrite malformed checkpoint markers,
or claim that extension file safety restricts unrelated model shell commands.

`src/playbook.ts` exposes the packaged Python 3.11+ stage engine. Keep the engine
and playbook aligned with dotcodex `plugins/sdlc/skills/sdlc/`; only the assets
folder name differs. Run `tests/test_playbook.py` for phase and adapter behavior.
Real approvals come from a protected external verifier. Never add a local approve
action or treat fixture adapters as live service acceptance.
