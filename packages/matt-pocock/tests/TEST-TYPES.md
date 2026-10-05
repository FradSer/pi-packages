# Test type coverage — 2026-10-04

Compatibility baseline: Pi v1.0. Installed CLI used for these runs: 1.0.2; workspace extension SDK/TUI: 1.0.0.

The finite supported catalog is the inventory boundary. This report does not claim that every possible software task, provider, operating system or physical interaction has been tested.

| Surface | Coverage | Evidence level |
| --- | --- | --- |
| Resource and invocation classifications | workflow, utility, reference, asset; model, user, internal | Catalog-derived checks |
| Public entry types | 21 standalone capabilities, 5 workflow routes | Real external-model cases and actual Pi command tests |
| Workflow graph | 28 placements, 57 transitions, 16 eager dependencies, 68 disclosures, 3 aliases | Unit graph validation and actual Pi deterministic runtime |
| References | 122 standalone reference paths / 268 loads; 43 workflow reference cases | Actual Pi with deterministic provider |
| User entry | 26 command entries, 8 literal/control/menu cases | Actual Pi PTY |
| State and lifecycle | restore, session tree/compaction, supersession, concurrent prompt cancellation, active tools, abort | Actual Pi RPC/PTY and isolated unit fixtures |
| Dialog types | native list, input, prompt timeout; native list abort; TUI/native fallback | Real macOS osascript timeout/abort and Pi PTY; no physical acceptance clicks |
| Tool input values | null, boolean, number (integer/fraction), string, array, object; valid and malformed nested fields | Production TypeBox schemas plus actual Pi v1 validation/normalization differential |
| Developer tasks | discount, async cache, configuration cleanup, frontend, API, authorization, migration, performance, localization, paths, test design | Real external-model repairs and independent immutable acceptance |

## Developer acceptance boundaries

| Added task | Acceptance | Explicit limit |
| --- | --- | --- |
| Frontend | HTML escaping, Unicode, associated label/text input, unchanged public exports | Generated HTML only; no browser layout or assistive-technology claim |
| API | Method/MIME/body validation, precedence, JSON response, immutable request | Pure request function, no deployed HTTP service |
| Authorization | Active identity, tenant isolation, owner/admin roles, unknown role denial | Local predicate, no hosted identity system |
| Migration | Versioned transformation, unknown field preservation, input/nested identity, unsupported version rejection | No database writes or rollback deployment |
| Performance | First duplicate, identity, NaN strict equality, empty requests, measured ID-read budget | Operation counts; no wall-clock or memory benchmark |
| Localization | English/Chinese variants, fallback, integer/negative input contract | Finite specified locales, no full i18n product audit |
| Paths | Sibling prefix/traversal rejection, dot normalization, legitimate `..notes` child names | Absolute POSIX lexical paths, no symlink or Windows filesystem claim |
| Test design | Correct additive implementations accepted; plausible wrong/throwing candidates rejected | Finite behavioral probe set, no proof over arbitrary functions |

## Findings and repairs

Initial real-model outputs exposed three missing acceptance boundaries: an exported HTML helper, rejected `..notes` paths, and Map equality/empty-request changes in an indexed lookup. Replaying those exact candidates against strengthened immutable acceptance reproduced three failures. The defective task baselines remain intentionally RED; corrected candidates are generated afresh by Pi.

The verification tool now exposes bounded redacted test diagnostics so reports can use observed failures and operation counts. Independent review reproduced secret-prefix leakage at the output truncation boundary and an early `process.exit(0)` false pass. Regression checks preceded both repairs. Completion is detected from a named test event in the trusted Node TAP reporter, independent of the 4 KB stored diagnostic limit. Candidate stdout is reported as comments; a reproduced marker-print-and-exit attempt now fails. The marker detects omitted acceptance execution; it is not a proof against a malicious program forging test output.

A real workflow review stranded itself because the exact state-contract call list included transitions/references but omitted terminal actions. The list now includes completion and cancellation explicitly. Catalog guidance also supplies a concrete valid gateway call for every route and model capability, with schema-error recovery instructions; user-only capabilities remain excluded from that model catalog. Root object properties expose every mode/action while preserving strict operation branches. Nullable root hints preserve Pi v1 optional-null handling: 39,290 finite argument combinations have identical schema acceptance, actual Pi acceptance and normalized results. The non-nullable mutation produces 109 differences and is caught by regression. A teaching run repaired application code despite an initial learning request; the teaching procedure now requires a separate implementation request for application repairs.

## Reproduction

Run `type_inventory.py` for the catalog-derived inventory. `expanded-type-cases.json` contains the eight additional real developer tasks. `real-model-cases.json` covers standalone/route entry cases, and `developer-journey-cases.json` covers three multi-turn development journeys. `real_model_live.py --list --cases <file>` is inert; `--all` starts real model calls only when explicitly requested.

Actual run results and preserved failures are recorded in `test-type-results.json`. Pending learner/product choices are expected `awaiting_user` outcomes, not completed implementations. Historical reports retain their original evidence and are not overwritten.

## Recorded results

- 67 real external-model attempts across 39 distinct cases. Latest outcomes: 31 passed and 8 expected awaiting_user. All 7 initial/intermediate failed attempts remain in the machine report.
- Eight added developer types pass independent acceptance after the reporter change; all three multi-turn journeys pass.
- Package suite: 238 passed in 103.05s (0:01:43). Typecheck, installed-package wiring and dry-run packaging pass.
- Actual Pi deterministic runtime: 271 tool executions, 3 expected rejections; all catalog reference, command, restore and lifecycle checks pass.
- Independent security/interface review closed the reproduced diagnostics, completion and optional-null regressions.
