# Align memory and harness ownership layers

## Problem Statement

Continual learning currently presents two different ownership models. Harness policies have four layers, including a user-personal file, while memory behaves as a project-scoped canonical store with a public mirror. This makes it difficult to predict where learned behavior lives, which source wins, and which files consolidation may mutate.

The desired product model is one consistent three-layer system for both memory and harness: user shared, project shared, and project personal. Automatic consolidation must learn into the project-personal layer while treating shared layers as read-only inputs.

## Solution

Expose the same ownership and precedence model on both continual-learning surfaces:

1. User shared
2. Project shared
3. Project personal

Resolve addressable entries from broadest to narrowest, with project-personal values winning over project-shared values and project-shared values winning over user-shared values.

Remove the harness user-personal layer entirely. Introduce explicit user-shared, project-shared, and project-personal memory roots. Consolidation reads the resolved surface but applies memory and harness changes only to their project-personal targets through the existing parent-owned validation, atomic-apply, and receipt pipeline.

## User Stories

1. As a Pi user, I want memory and harness to use the same layer names, so that I can reason about both features consistently.
2. As a Pi user, I want user-shared knowledge to apply across projects, so that durable general lessons do not need to be copied into each repository.
3. As a project contributor, I want repository-safe memory in a project-shared directory, so that the team can version shared project knowledge.
4. As an individual contributor, I want personal project memory in a local directory, so that private or personal knowledge is not committed.
5. As a project contributor, I want shared harness policy in the repository, so that tool-call rules can be reviewed and versioned.
6. As an individual contributor, I want learned harness changes to remain project-personal by default, so that automation does not silently modify shared policy.
7. As a user, I want narrower memory entries to override broader entries by filename, so that project-specific facts can refine general knowledge.
8. As a user, I want narrower harness declarations to override broader declarations by name, so that project-specific behavior can refine general policy.
9. As a user, I want the obsolete global personal harness file ignored, so that there is no hidden fourth precedence layer.
10. As a user, I want `/harness --global` to target the remaining user-shared file, so that the command still has an explicit global destination.
11. As a user, I want `/memory` to open the project-personal memory directory, so that manual edits go to the same layer consolidation owns.
12. As a user with existing project-scoped memory, I want it migrated into the new project-personal directory without overwriting explicit new-layer content, so that the model change does not discard learned knowledge.
13. As a user, I want automatic consolidation to leave shared memory untouched, so that learned changes do not bypass review.
14. As a user, I want automatic consolidation to leave shared harness policy untouched, so that learned rules do not bypass review.
15. As a user, I want validation and receipts for memory and harness application, so that planner output alone never proves mutation succeeded.
16. As a user, I want indexes rebuilt independently for every memory layer, so that each layer remains inspectable.
17. As a user, I want `MEMORY.md` excluded from injected entries, so that indexes do not become recursive content.
18. As a user, I want non-project directories to avoid project memory roots, so that workspace parents and configuration directories do not accumulate accidental state.
19. As a user, I want no compatibility fallback to the removed harness user-personal file, so that stale configuration cannot silently affect behavior.
20. As a maintainer, I want documentation and command diagnostics to describe the actual three-layer model, so that runtime and documentation remain aligned.

## Scenarios

```gherkin
Feature: Shared ownership layers for memory and harness

  Scenario: Harness resolves exactly three layers
    Given harness declarations exist in the user shared, project shared, and project personal files
    When harness configuration is loaded
    Then project personal overrides project shared
    And project shared overrides user shared
    And the removed user personal file is ignored

  Scenario: Global harness creation targets user shared
    Given the user invokes /harness with --global or --user
    When the creation target is resolved
    Then the target is the user shared harness.json file

  Scenario: Memory resolves exactly three layers
    Given memories with the same filename exist in user shared, project shared, and project personal roots
    When active memories are loaded
    Then the project personal content is injected
    And the broader duplicate contents are not injected

  Scenario: Memory retains non-conflicting entries from every layer
    Given each memory layer contains a distinct valid memory filename
    When active memories are loaded
    Then all three entries are injected with their effective source layer

  Scenario: Consolidation writes memory only to project personal
    Given resolved memory candidates come from any of the three layers
    When a verified consolidation plan is applied
    Then mutations are written only to the project personal memory root
    And user shared and project shared bytes remain unchanged

  Scenario: Consolidation writes harness only to project personal
    Given a verified harness plan is returned
    When the parent applies the plan
    Then only the project personal harness file is mutated

  Scenario: Existing scoped memory migrates safely
    Given legacy project-scoped memory exists below the agent memory directory
    And the new project personal root is missing or lacks some filenames
    When memory paths are initialized
    Then legacy files are moved into project personal
    And existing project-personal files are not overwritten
    And the legacy project-scoped source is removed after a successful migration

  Scenario: Project memory roots require a canonical Git root
    Given the current directory is not the canonical Git worktree root
    When memory paths are resolved
    Then project shared and project personal memory roots are disabled

  Scenario: Index files are layer-local metadata
    Given memory entries exist in one or more layers
    When indexes are rebuilt
    Then every enabled layer has its own MEMORY.md
    And no MEMORY.md is loaded as a memory entry

  Scenario: No-context consolidation skips context-dependent phases
    Given the user invokes /consolidate no-context
    When memory consolidation completes
    Then harness and AGENTS.md consolidation are skipped as before
```

## Implementation Decisions

- The common domain model is three layers: user shared, project shared, and project personal.
- Harness removes its user-personal path and source label. There is no fallback read or migration from that removed file.
- The harness global command flags target user shared. Shared/project flags continue to target project shared; the default remains project personal.
- Memory introduces explicit roots for all three layers. The user-shared root is the agent memory root itself; operational subdirectories and JSON/lock artifacts are naturally excluded by the strict Markdown filename policy.
- Project memory roots are enabled only when the current directory is the canonical Git worktree root. They are `.memory` for project shared and `.memory.local` for project personal.
- Memory precedence is filename-based and matches harness name-based precedence.
- Memory consolidation takes all effective layers as inputs but applies selected rewrites and deletions only to project personal. Shared layers are immutable during automatic consolidation.
- Privacy is represented by ownership layer rather than a public mirror marker: project-personal memory is local and project-shared memory is repository-safe.
- Existing hashed project memory is migrated once into project personal. Explicit project-personal content wins conflicts. The runtime does not retain a read fallback after migration.
- Parent-owned locks, immutable snapshots, bounded planner output, schema validation, atomic application, rollback, and receipts remain mandatory.
- AGENTS.md extraction that produces durable memory targets project personal.
- Terminology in user-facing diagnostics changes from harness/public memory to user shared/project shared/project personal memory.

## Testing Decisions

- The highest existing seams are retained: feature scenarios plus Python source/runtime harness tests around path resolution, loading, consolidation application, guardrail configuration, and command targeting.
- Guardrail tests verify observable source precedence and command destinations, not private helper structure.
- Memory loader tests construct all three roots and verify effective injected entries by filename and source.
- Consolidation tests snapshot shared roots before application and assert byte identity afterward while validating project-personal output and receipts.
- Migration tests cover conflicts, missing destinations, index rebuilding, and source cleanup.
- Existing symlink, path-escape, output-bound, lock, rollback, shutdown, and privacy tests remain applicable and are adapted to the new layer vocabulary.
- Package tests, root tests, strict TypeScript checking, package dry-run, live install check, and a live Pi smoke run are required before completion.

## Out of Scope

- Automatically promoting project-personal memory or harness rules into shared layers.
- Adding a user-personal layer back under a different name.
- Changing the declarative guardrail schema or matching engine.
- Changing the AGENTS.md byte-budget policy.
- Preserving stale runtime behavior from `~/.pi/agent/harness.local.json`.
- Supporting project memory roots for arbitrary repository subdirectories or workspace parents.

## Further Notes

The change intentionally replaces the old canonical-store/public-mirror memory concept. Documentation and code should use ownership-layer vocabulary consistently and avoid describing project-shared memory as a synchronized mirror of private memory.
