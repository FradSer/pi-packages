# Two-pair public coverage retest

Given the unchanged original no-plugin drafts for Ant Design 54813 and DSPy 8105,
when two independent Docker Pi 1.0.4 workflows use DeepSeek v4.1 Flash (high),
then compare final strict scores, completed workflow reports, native fresh proof,
requirements mapped to executable tests, and incremental estimated cost.

This supersedes the stopped study only for a new two-task retest. Preserve all
old receipts. These tasks were selected explicitly before this retest and have
previously been inspected; this is exploratory, not held-out evidence.

- Shared limits: 1200 seconds and 80 model requests per arm. Review receives one
  read-only review up to 300 seconds, followed by repair. E2E receives no host API
  verification shortcut: the Pi agent itself must author focused checks, invoke
  native e2e_verify, fix observed failures, and reverify after changes.
- Both arms receive the same public-only four-clause feature and fixed adapter.
  Both may author tests and .e2e/coverage.json (clause -> command and test names).
  E2E calls the plugin; review runs the same adapter directly. Neither sees
  hidden tests/outcomes, oracle patches or the other arm's findings.
- Missing coverage mappings fail deterministic checks. Mappings are agent authored;
  their semantic adequacy still requires report inspection and is not independent
  proof of complete requirements. The original public suite remains mandatory.
  Reuse commands across clauses to avoid redundant full-suite execution.
- Fix real defects only. An unchanged correct draft is a valid outcome. Stop
  repeated inspections without new evidence; a collector also terminates six
  consecutive identical tool observations, marking the workflow incomplete.
  A changing but unproductive loop may still reach the shared cap; no universal
  semantic progress detector is claimed. Reserve final verification/report time.
- Flush redacted complete events to durable files during execution. Timeouts,
  aborted final responses and request exhaustion are incomplete workflows even
  when the process exits zero. Always grade captured code separately.
- Stage cleanup, image/HEAD/runtime/seed provenance, strict graders and unknown
  usage accounting retain the original protocol. No outcome-driven retries.
- A strict pass, a fulfilled public feature, a fresh verification and a completed
  model report are separate results. Do not promise improvement from two pairs.
