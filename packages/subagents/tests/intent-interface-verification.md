# Intent interface verification

Date: 2026-10-02.
Status: local implementation complete. No publication or commit occurs.

## Scope

The model interface has five operations and an explicit input delivery enum.
Saved identity, display label, and exact session address remain separate.
The legacy model selection and exported library API remain compatible.
Reported answer rows use native Markdown without changing result bytes.
A narrow child contribution classifies the known premature stream-close error for native Pi retries.
Read @packages/subagents/VISION.md for the authoritative execution contract.

## Independent review

Reviewer: review-intent-interface, turn 3, delivered 2026-10-02T17:36:46.400Z.
The reviewer confirms closure of all four earlier blockers and finds no remaining scoped P1/P2 defects.
The reviewer runs 53 focused checks and both real-host/transport-parser regression modes.
The reviewer also probes failed startup, exact control ownership, and steering correlation.
The original turn 1 stream failure is not a review verdict.

The fixed review findings are:

- Drain hosted predecessor reports before changing input IDs or settlement flags.
- Capture the steered input ID before awaiting acknowledgement.
- Grant accepted-input authority only after positive exact-owner startup validation.
- Restore one tool family for existing history without recorded selections.

Feature scenarios and failing regression tests precede each fix.
The hosted race fixture uses real host logic and transport parsing with mocked process operations.
It proves that ordering defect, not its production frequency.

The stream recovery reviewer separately finds no confirmed P1/P2 defects.
Four native parent print/TUI cases verify unanswered delivery with disabled or exhausted retry.

## Verification

All 669 subagent checks pass in disjoint groups:

- 587 non-live checks.
- 79 native print/RPC/TUI checks.
- 3 private-history and temporary-resident checks.

The following additional checks pass:

- 123 pi-kit checks.
- 103 scoped team and root checks.
- Root and pi-kit TypeScript checks.
- Packed manifest checks for 18 packages.
- Installation checks for 17 installed packages and 18 settings entries.
- Git diff whitespace checks.

After review delivery, 37 focused and native checks and two hosted parser modes pass again.
These reruns overlap earlier groups and are not added to their totals.
The 12 scoped source hashes below stay unchanged throughout that final verification.

## Limits

Unrelated task-contract checks still fail; no whole-workspace clean result is claimed.
No comparative model A/B benchmark or production connectivity guarantee is claimed.
Loopback native providers use isolated temporary settings, not user credentials.
Cross-parent history ownership and legacy user-data migration remain separate decisions.
Existing live children do not acquire newly loaded extension code.
Reload loads package edits; a new parent conversation uses the intent family by default.
A branch that recorded the retired `agent` selection receives the intent family; the retired
name is never selectable and no compatibility adapter remains (ADR-0008).

## Checked source hashes

```json
{
  "packages/subagents/src/child-execution.ts": "fe3b5d9e03b29b9f76977f90afc2e589c353dc223992c82f509c377a092bd679",
  "packages/subagents/src/intent-tools.ts": "12c828848d23b547ee2ff683dc650bc059b92b3cfff0ff10e6d237849375982a",
  "packages/subagents/src/input-sequences.ts": "1a56126a13197352a6fadaf5a39e024c2d7705424f1033328a7e551329352cba",
  "packages/subagents/src/tool-activation.ts": "4715a24f6a310bc27c53cd1160b2e67e6e8a9e6cdf7efd52175badd030209169",
  "packages/subagents/src/session-result.ts": "9b63fc5bce572642bc12bc3c55fb86502e441b663626b59cb9e99b876dbad57e",
  "packages/subagents/src/extension.ts": "15c8ae71cdc57f2c469761b109e79464ef233346c5329e7fe1fbbfd5c59f5f98",
  "packages/subagents/src/stream-recovery.ts": "56a3d416a0afbaa08df2012864e69b9c919dbf8679fac87a8e114bc2bd74ef75",
  "packages/subagents/src/roster.ts": "d362fd050bbde8a4f476242de934827d8850e0fb02210a0174fc0e0bc492d0b6",
  "packages/subagents/src/agent-output.ts": "f3b7e523838bd905665568cf4dc3173d3c2d49b9cb83e64aa9cc9806ec73eb1b",
  "packages/agent-teams/src/agent-host.ts": "f93a47c187ec59f7d141b9f2b7d5f5e18270d1d00fbd52ef866c7d7330dad885",
  "packages/agent-teams/src/team-machine.ts": "ddbc57adbc75552b08ee51506f0117b2954c1bd6855c80158fc4ee5c7d249416"
}
```
