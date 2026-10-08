# pi-e2e

Judge whether an end-to-end Gherkin `.feature` scenario was fulfilled by one test run.

Code decides the clauses you can check exactly. The TypeSafe **Jev** model
answers only the clauses that need a semantic reading of the evidence. The final verdict
is composed in code with probability gates, so an uncertain answer becomes a
review and never a pass.

## Why

A BDD / end-to-end suite fails in two different ways, and the tools answer them differently:

- **A clause that states an exact fact** — "the workspace plan is Pro" — belongs
  in code. A model call adds cost, latency, and a chance to be wrong about a
  string comparison.
- **A clause that states a business intent** — "the billing page shows an amount
  that covers only the remaining days of the current billing period" — needs the
  clause text read together with the real invoice numbers of that run. That is a
  judgment, not a comparison.

This package keeps the first kind in code and sends only the second kind to Jev.

## Install

```bash
pnpm add -D @fradser/pi-e2e
```

Set `TYPESAFE_API_KEY` to let Jev answer the clauses without a check. The package
never takes a key as a flag, so a key cannot leak into a transcript.

## Use it from the CLI

Run via `pnpm exec tsx`, `npx tsx`, or `bun` (Node.js native type stripping skips `node_modules` by design):

```bash
pnpm exec tsx node_modules/@fradser/pi-e2e/src/cli.ts verify \
  --feature examples/billing.feature \
  --evidence examples/billing-evidence.json \
  --offline --report-html report.html
```

Or directly from source:

```bash
node src/cli.ts verify \
  --feature examples/billing.feature \
  --evidence examples/billing-evidence.json \
  --offline --report-html report.html
```

Options: `--scenario <name>`, `--clause-gate <0..1>`, `--verdict-gate <0..1>`,
`--report-md <path>`, `--report-html <path>`, `--json`.

Exit codes are stable for CI: `0` fulfilled, `1` unfulfilled, `2` needs review.

## Use it from Pi

The extension registers one command:

```
/e2e <feature.feature> <evidence.json> [scenario name]
```

Or with the optional `verify` subcommand:

```
/e2e verify <feature.feature> <evidence.json> [scenario name]
```

It runs the same core and notifies the verdict. It never asks for a credential.

### Automatic acceptance workflow

Pi adds a bounded acceptance checkpoint only for a feature path this turn touches directly or the user names explicitly. A feature that changes in another package does not trigger it. Implementation-file activity invalidates a feature only when this turn already involves that feature. The agent must inspect project instructions, scripts, test setup, and existing tests. A failed verdict and changed-feature directions share one checkpoint; neither hides the other. The same checkpoint is not repeated without relevant progress or a new verification result. Automatic continuation stops after two attempts and unresolved acceptance is reported as `needs_review`.

The harness only prompts the model. It does not run tests or create evidence. A checkpoint carries its own marker, so Pi does not read it back as a user request for acceptance.

Only a successful fresh test process can clear the checkpoint. Inline JSON, existing evidence files, and `/e2e` still evaluate supplied evidence, but cannot certify its origin or clear acceptance. The native tool returns `verifiedRun` separately from the composed `status`.

Configure the project's authorized adapter **before calling e2e_verify** in `.e2e/runner.json`:

```json
{
  "executable": "node",
  "args": ["tests/acceptance-adapter.mjs"],
  "adapterFiles": ["tests/acceptance-adapter.mjs", "tests/evidence-serializer.mjs"]
}
```

The adapter runs the actual suite and writes its `Evidence` JSON to the fresh path supplied in `PI_E2E_EVIDENCE_PATH`. It must exit zero only when execution succeeded; it must observe the actual application and never copy example evidence. It must also declare a `checks` entry for every Then clause its run can decide, because a clause with neither a check nor a model answer stays unjudged and the verdict stays `needs_review`. Without checks, offline verification cannot certify acceptance; online semantic clauses still require sufficient Jev answers. List the adapter and **all evidence-producing dependencies** in `adapterFiles` (1–64 file or directory paths, at most 2000 regular files, each at most 1 MiB and 32 MiB combined). Adapter declarations and test quality are the project's trust boundary; this package cannot prove that a pre-existing adapter tests the right business behavior.

This repository's adapter keeps suite links in `tests/scenario-behavior-map.json` and clause observation bindings in `tests/scenario-observation-map.json`. The Goal seed binding runs `tests/observe-goal-seed.mts` against a fresh temporary session's real `/goal` handler. It observes goal creation, delivery options, and the complete request body against an independent approved contract. Bindings must match all Given/When/Then and background steps, and producers and their dependencies must be listed in `.e2e/runner.json`'s `adapterFiles`. Unbound suites emit no clause checks; changed steps or an unregistered producer stops the adapter.

Invoke the native tool with the matching command:

```json
{
  "feature": "features/checkout.feature",
  "scenario": "Checkout succeeds",
  "runner": { "executable": "node", "args": ["tests/acceptance-adapter.mjs"] }
}
```

Do not combine `runner` and `evidence`. Optional `runner.timeoutMs` is 1–600000 ms (default 120000, or the configured timeout). Use `offline: true` for scenarios fully covered by deterministic checks; otherwise Jev judges the remaining clauses.

Each e2e_verify call captures the current configuration and adapter fingerprints, then executes a fresh test process. You can repair implementation, tests or an authorized adapter and retry repeatedly in the same turn. Changes during a single attempt invalidate its evidence; the error names the changed adapter files. A new user turn invalidates in-flight observers. Accepted runs are checked again before settlement, including unchanged features the user asked to verify. Repairs after a pass withdraw its proof until a fresh run passes. Every scenario in an explicitly requested feature must pass before the feature is accepted. Automatic continuation is bounded to two reminders; manual verification calls have no per-turn limit.

Runner failures, aborts, timeouts, excessive output, stale turns, missing/invalid evidence, symlinks, and non-regular output cannot certify acceptance. Evidence and combined stdout/stderr are each capped at 1 MiB. Private temporary evidence is removed after each call. Timeout/abort kills the process group on macOS/Linux; Windows process-tree behavior has not been validated.

The extension compares bounded `.feature` snapshots at turn start and settlement to detect changes from shell commands and other tools. A changed feature triggers a checkpoint only when its package has current-turn file activity or the user named its path. Unrelated feature changes in other packages do not trigger it. The scan skips `.git`, `node_modules`, and `.pi`; it checks at most 2000 feature files (1 MiB each, 32 MiB total) and 20000 directories, and it reports incomplete scans. Every scenario in a changed feature must receive a fulfilled fresh-run verdict. Scenario names must be unique, and each scenario must contain a Then clause.

## The evidence file

```json
{
  "checks": [
    { "clause": 1, "op": "equals", "path": "workspace.plan", "value": "pro" }
  ],
  "triage": [
    { "id": "duplicate_charge", "description": "the payment method was charged more than once" }
  ],
  "run": {
    "suite": "tests/billing/upgrade.e2e.ts",
    "steps": [],
    "observations": { "workspace": { "plan": "pro" }, "invoice": { "amount_usd": 96 } }
  }
}
```

- `checks` bind to Then clause numbers, 1-based, in file order. Operators:
  `equals`, `notEquals`, `contains`, `matches`, `exists`. A path reads
  `run.observations` and supports `invoice.amount_usd` and `payment_events[0].id`.
- `triage` items each become their own question, so several faults can light up
  at once. One "which single cause" question would spread its probability
  instead.
- `run` is the evidence the model reads. Keep it text and JSON: Jev reads text
  only, so screenshots have to become a description or a value first.

## How the verdict is composed

1. A declared check fails, so the scenario is `not_fulfilled`. Code is final.
2. A clause with no check and no answer is `unjudged`, so the verdict is
   `needs_review`.
3. A Jev clause under the clause gate counts as unsettled, not as a failure.
4. A model verdict under the verdict gate becomes `needs_review`.
5. Only above the gate does the model's choice set `fulfilled`,
   `partially_fulfilled`, or `not_fulfilled`.

The same shape appears in the TypeSafe citation cookbook: screen with a
deterministic check first, ask one Choice question second, and send anything
below the confidence gate to a person.

## Limits of this MVP

- The Gherkin subset covers Feature, Background, Scenario, tags, and plain
  steps. Scenario Outline, Examples, Rule, tables, and doc strings are rejected
  with the line number instead of being read as prose.
- One scenario per call.
- Gates are policy you set. The defaults (0.8 and 0.6) are starting points, not
  measured values for your domain.
- Jev reads text, so an image-only failure needs a description before it can be
  judged.

## License

MIT

Default tool results show complete wrapped reports and errors, without ctrl+o or clipping. Checkpoints use the shared `[e2e] continue` row; unresolved normal settlement uses `[e2e] waiting`. User cancellation adds neither a continuation nor a generic acceptance warning. See [TUI cases](TUI.zh-CN.md).

### Project observation producers

In this repository, `tests/run-feature-suites.mjs` selects linked tests using
`tests/scenario-behavior-map.json`. Optional scenario-specific producers are
registered in `tests/scenario-observation-map.json`. Each binding includes the
exact Given/When/Then steps; edits require an updated observation contract. The producer
must appear in `.e2e/runner.json` `adapterFiles`. Only observations produced by
that fresh invocation declare checks; linked suite success alone does not. The
Goal seed producer invokes the real `/goal` handler in an isolated no-goal
session and checks creation, the objective-writing request, and quoted input.

The tool judges one scenario per call. Checkpoints list the remaining scenario
names; whole-feature acceptance requires all of them. A verified fulfilled tool
report completes acceptance without a duplicate success notification. Evidence
gaps request observations/checks; behavioral failures request implementation
repairs. Plain `pwd` and restricted `git status` calls do not invalidate proof,
while unknown shell commands remain conservatively invalidating. File and
adapter drift checks still run at settlement.

### Complete Goal contract coverage

The current simplified Goal architecture is authoritative. All 106 former
scenarios remain in `tests/legacy-goal-scenarios.json`; the migration table
`tests/goal-scenario-migration.json` records retained, revised and retired
requirements and their current targets. The current feature contains 179 cases
and 718 atomic Then predicates. This coverage statement applies to Goal only.

`tests/observe-goal-harness.mts` executes real behavior harnesses in fresh
processes. The shared assertion observer records each native assertion's actual
and expected values, operator, source expression and invocation count. Frozen
harness hashes and assertion selectors reject missing, changed or extra
witnesses. A clause checks its individual native assertion outcome; suite exit
status never substitutes for it. Imported runtime modules and observer code are
also fingerprinted through the registered adapter dependencies.

After reviewing a deliberate fixture/contract change, run
`pnpm exec tsx packages/e2e/tests/sync-goal-contracts.mts --write`.
Without `--write`, the command checks consistency and changes no files.
The generator is an explicit maintenance action, never part of acceptance.
Regeneration cannot establish semantic coverage of old requirements; review the
migration table and add behavior predicates for still-valid requirements.

Run exhaustive fresh acceptance and checkpoint validation with:

```bash
pnpm exec tsx packages/e2e/tests/verify-goal-contracts.mts /tmp/goal-coverage-report.json
```

Every scenario runs the configured project adapter and must be fulfilled with
fresh proof and zero model questions. The final feature checkpoint must clear.
Runs do not reuse receipts. Native CLI/TUI acceptance uses a scripted provider;
these results do not establish real-model decision quality.
