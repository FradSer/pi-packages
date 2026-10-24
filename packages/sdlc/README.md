# pi-sdlc

Capture user intent and keep the next session ready to resume. This package ports
the complete dotcodex SDLC workflow to native Pi lifecycle events and the `sdlc`
tool. Python 3.11+ and Git are required. It adds no model provider or background
agent. Configured review, eval and diagnosis adapters can make model calls.

## Install

```bash
pi install npm:pi-sdlc
```

From a local checkout before publication:

```bash
pi install /absolute/path/to/pi-packages/packages/sdlc
```

The installed package bundles its workflow and templates. It does not require a
dotcodex checkout. Development and native acceptance use Pi 1.3.0; published Pi
core imports are host-supplied peers. Restart Pi after installation.

## Full lifecycle

Read [the playbook](references/playbook.md) for all six course stages and
[the engine contract](references/commands.md) for configuration and commands.
The `sdlc` tool supports init, status, advance, rewind, handoff, check, eval,
review, deploy, metric and archive. The stage order is intent, design, plan,
build, test, review, deploy and maintain. Use SPEC.md, PLAN.md and REVIEW.md
alongside the existing intent and handoff. The bundled engine can also run directly:

```bash
python3 packages/sdlc/scripts/sdlc.py init --cwd /path/to/worktree
python3 packages/sdlc/scripts/sdlc.py status --cwd /path/to/worktree
```

Approve each artifact through an independent verifier configured in the protected,
external `SDLC_POLICY_FILE`. The tool cannot create an approval. Configure real
project checks and an independent historical-task eval suite before plan approval.
Changes to source, policy or agent setup invalidate old verification evidence.
Independent review checks bugs, security and intent/spec/plan compliance. Important
findings block progression. Releases pin the committed version, verify current
code owner and environment approvals, check health and roll back on failure.
Metric detection uses deterministic bands and drift rules, with new intents in
`.sdlc/inbox` for triage. A task archive keeps the artifact chain separate from
the next change. Missing adapters leave a visible blocked stage.

The native edit guard protects planning-stage writes and routes release tools
through the engine. Shell, alternate APIs and disabled extensions still need
managed permissions, CI checks and service-side authorization. Use isolated CI
runners and protected branches. Local state is not a tamper-proof audit service.

## Records

The native `input` event appends the user's original text to `INTENT.md` in the
working directory, before host template expansion. Steering during work and queued
follow-ups are retained too. For SDK user runs without an input event, the extension
uses the submitted user prompt. Generated extension messages are not user intent.
The document uses the [course format](https://academy.claude.com/courses/ai-native-sdlc-playbook/capture-intent):
an Intent title, an Author and Status line, and exactly these English sections:
Problem, Proposed outcome, Affected users and systems, Constraints, Open questions.
The body uses the user's language. Unknown authors remain `Not provided` and
the status stays `draft` until explicit approval. Quoted source requests remain
in collapsed details blocks. Corrections preserve prior requests.

The [workflow](references/workflow.md) requires the model to read `HANDOFF.md`
and `INTENT.md` before work and update the handoff before finishing, a planned
pause, or an agent handoff. It must checkpoint meaningful progress, keep one
current state under 200 lines, link to `INTENT.md`, and avoid repeated requirements,
prompts, final responses, and per-turn history. The current state includes execution
decisions, observed checks and results, blockers, and concrete next steps.

`before_agent_start` injects this workflow through structured prompt sections
without replacing other extensions' sections. Custom messages are not user intent;
custom continuation runs in a managed session retain the handoff workflow.
`agent_settled` replaces one latest lifecycle block. Abort marks interrupted work;
model errors remain explicit. `session_shutdown` marks an active run interrupted.
It does not overwrite an already settled checkpoint. Unexpected interruptions
cannot run model work in advance, so the last evidence checkpoint remains.
A turn ending is not proof of task completion.

The model reads relevant legacy `CONTEXT.md` progress and transfers only current
decisions, evidence, blockers and next steps. The extension does not write or remove
that legacy file. Review retained source text before sharing or committing it.

## File safety

Cooperating package writers use pi-kit's exclusive JSON lock publication.
Linked or non-regular documents and malformed lifecycle markers are rejected.
Checked Markdown replacements use a private temporary file and atomic rename;
pi-kit supplies JSON persistence but has no checked Markdown writer. Recording
errors are reported through Pi notifications or headless stderr and run guidance.
An interrupted writer can leave `.sdlc-write-lock.json`; inspect its owner before
removing it. The extension never steals a lock.

The lock does not cover model edits or unrelated shell commands. Use separate
working directories for parallel tasks. The file checks are not a process sandbox.
The workflow makes handoff maintenance mandatory instructions; it cannot prove
semantic summary quality or enforce a write against explicit user restrictions.

## Verify

```bash
uv run --with pytest python -m pytest packages/sdlc/tests -q
pnpm typecheck
pnpm --dir packages/sdlc pack --dry-run
uv run --with pytest python packages/sdlc/tests/live_sdlc.py --output /tmp/pi-sdlc-e2e
```

Native E2E uses the real Pi print/RPC entrypoints, real tools and files, and a
deterministic in-process provider with network transport denied. It proves lifecycle,
tool execution and artifact behavior. It does not establish real-model instruction
following, semantic quality, or physical-terminal interaction.
