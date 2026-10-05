# RED evidence for the goal audit

Each confirmed defect was reintroduced into the real tree, the matching regression was run,
and the file was restored byte-for-byte. Fingerprint `8368a916d35291ac9736b6c031e3a257eebfc90175354791afcf414895017095`
(SHA256 over a sorted listing of `packages/goal/src/*.ts` as SHA256, two spaces, path, newline) was
recorded before and after the runs and is identical, so the frozen candidate was restored completely.

Method correction: an earlier attempt mutated a temporary copy and pointed the regression at the repository
tests. Those tests read `PACKAGE`/`REPO` from their own file location, so a temporary copy is invisible to them
and a mutation there cannot reproduce RED. That earlier claim of mutation coverage was unsound and is withdrawn.
The runs below mutate the tracked file in place and restore it in a `finally` block verified by content
comparison.

## RED 1 — dead `autoSelectSingleGoal` setting

Mutation: `src/settings.ts`, `autoSelectSingleGoal?: boolean;` re-added after `disableCheck`.

```
AssertionError: settings.ts declares autoSelectSingleGoal but no runtime module reads it
```

## RED 2 — dead `thinkingLevel` setting

Mutation: `src/settings.ts`, `thinkingLevel?: string;` re-added after `model`.

```
AssertionError: settings.ts declares thinkingLevel but no runtime module reads it
```

## RED 3 — ghost `taskIndex` import

Mutation: `tests/goal_store.mts`, `import { taskIndex } from "../src/record.ts";` re-added.

```
AssertionError: unresolved test imports: goal_store.mts: record.taskIndex
```

## RED 4 — load-bearing claim line removed

Mutation: `tests/goal_scheduling.mts`, the claim and its assertion removed again.

```
AssertionError: goal_scheduling.mts stderr:
```

## Restoration

```
fingerprint before: 8368a916d35291ac9736b6c031e3a257eebfc90175354791afcf414895017095
fingerprint after:  8368a916d35291ac9736b6c031e3a257eebfc90175354791afcf414895017095
RESTORED_IDENTICAL True
```
