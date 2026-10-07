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
