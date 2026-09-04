# pi-matt-pocock

`pi-matt-pocock` provides one `/matt-pocock` menu and a catalog-backed capability gateway for engineering workflows and focused procedures adapted from `mattpocock/skills`.

## Installation

```bash
pi install npm:pi-matt-pocock
```

## How it works

`/matt-pocock` starts or manages persisted workflows and runs standalone capabilities. A single `procedureCatalog` manifest classifies bundled resources as workflow procedures, standalone capabilities, references, or assets, and defines their dependencies, disclosures, workflow placement, and legal transitions.

The baseline `matt_pocock_workflow` gateway starts a workflow, runs a model-reachable standalone capability, or loads a reference disclosed by one. While a workflow is active, `matt_pocock_active` and `matt_pocock_ask` are progressively enabled for transitions, reference loading, completion or cancellation, and structured user decisions.

Each workflow has a stable `workItemId` and persisted `active`, `completed`, or `cancelled` status. Procedure bundles include mandatory `requires` dependencies, expose optional `discloses` references without loading them, identify every body with a stable `source:procedure/<id>` source id, and are capped at 64 KiB. Workflow transitions are limited to the current catalog placement's `allowedNext` set.

Procedures remain internal Markdown resources; the package ships no child `SKILL.md` files, so generic names such as `tdd`, `research`, and `code-review` do not become globally discoverable skills.

See the detailed [中文架构说明](ARCHITECTURE.zh-CN.md), the upstream [selection metadata](upstream-selection.json) and [sync rules](UPSTREAM.md), and the deliberately deferred items in [TODO.md](TODO.md).
