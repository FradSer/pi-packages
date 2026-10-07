# Lossless evidence structural view research

Status: real component experiment completed; no demonstrated improvement and
no production adoption.

The preceding real Jev decomposition study increased false holds. This study
changes only the representation of evidence, preserving the original questions,
criteria, every original entry, conditions and ordering. A derived named view
copies message fields with exact source paths. Tool-result links refer only to
earlier assistant tool calls in the same evidence surface; duplicate IDs remain
ambiguous and missing IDs remain unresolved. Error flags are copied literally,
without inferring exit codes or verification success.

The fixed corpus contains twelve authored bilingual development samples and one
reused real project failure generated with
`cli-proxy/opencode/deepseek-v4.1-flash`. The original failure request was
reconstructed with an offline SDK fixture. It is not an archived on-wire request.
All thirteen original requests and thirteen structural variants are prepared
before inference. The largest serialized request is 54398 UTF-8 bytes, within
the conservative 64000-byte research bound. This is not token measurement.

Prospective protocol: model `jev-1.13.0`, one attempt per arm per sample, no retry;
unchanged confidence 0.8 and selected probability 0.9 gates; missing, invalid or
wrong-version responses are incomplete. Report only complete pairs for quality
comparisons and separately count incomplete pairs, valid holds, mistaken
compatibility, lost previous valid outcomes, actual usage and durations. A
component improvement requires fewer false holds with no added false-compatible
outcomes or lost original valid outcomes. Any positive result still needs fresh
heldout samples and native full-path validation. No study result grants writes.

The frozen manifest caps inference at 26 requests, with a theoretical maximum
input-fee estimate of USD 0.069888 at the official 64000-input-token limit and
USD 0.042 per million input tokens. Billing remains unverified. Preserve failure
results and do not repeatedly query a failing case until it passes.

The source helper adds no file, network or credential access. Independent review
confirmed preservation and provenance behavior. Its four identified coverage
gaps now have direct passing tests: later calls, cross-surface references,
question count limit and multibyte request boundary. The updated tests required
a new `manifest-v2.json`; the original frozen manifest remains untouched.

For frozen paths and hashes, read
@packages/continual-learning/tests/evidence-structural-view-preflight.json.

## Observed result

Twenty-six attempts returned twenty-five valid pinned-model responses and one
URLError, without retry. Twelve complete pairs show one valid hold in each arm,
no false-compatible outcomes and no lost original valid outcome. The thirteenth
pair is incomplete and cannot count toward favorable accuracy. The prospective
component criterion is not met. Production remains unchanged.

The reused real failure selected compatible in both arms but remained below the
selected-probability gate: original confidence 0.62 / compatible probability
0.74; structural confidence 0.83 / probability 0.88. This is one diagnostic
signal, not proof of a general effect or justification to reduce the 0.9 gate.
The structural arm used 17078 input tokens versus 8911 for the original. Repeating
raw evidence alongside a view nearly doubles this case's input cost.

Known usage: 44444 input and 1426 output tokens; estimated input fee USD
0.001866648. One failed attempt has no usage and unknown cost. Median request
duration was 1076.5 ms; summed durations 32800 ms. This is direct official HTTP
inference, not live SDK inference. No Memory or Harness application occurred.

For diagnostics and raw immutable result provenance, read
@packages/continual-learning/tests/evidence-structural-view-results.json.

Postpaid independent review verified frozen hashes, all twenty-six attempt pairs,
request bytes, usage, metrics and privacy-safe diagnostic logs. Verification:
full package suite 1065 passed in 437.35 seconds; the seven cases added after its
collection pass in the focused 27-test run (0.18 seconds). TypeScript, nineteen
workspace packed manifests, target dry pack and diff checks pass. Production
runtime is unchanged; this does not supersede prior unrelated installation gaps.
