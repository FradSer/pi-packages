# Docker/native model study

Run this only when real-model execution is explicitly requested. It uses Docker,
Pi **1.0.4**, and the user's configured `cli-proxy/opencode/deepseek-v4.1-flash`.
The host-only transparent inference proxy retains upstream credentials outside the
image/container. Its expiring study token is never copied into evidence.

```sh
uv run --python 3.13 packages/subagents/tests/docker-study/run.py --output /tmp/subagents-study-104
uv run packages/subagents/tests/docker-study/score.py /tmp/subagents-study-104
```

Read `../../features/docker-memory-study.feature` for the scenarios. `study.ts` invokes the public intent
executor with real native RPC children; it does not stub provider replies.
`audit.ts` observes native tool calls/results and injected Memory indexes.
`parent-probe.py` separately lets the actual parent model select tools in a native
PTY and exercises expansion and narrow-width repaint. Parent tool selection is
not inferred from the direct-executor scenarios.

All authored identities, source fixtures, Memory and history belong to the
isolated study container. The script deletes only its own container and retains
its image and sanitized evidence. It does not edit real identities or histories.

The four paired heldout reviews are synthetic package-contract fixtures, not a
repository audit. Training requests a model-authored accepted capability with a
write grant; ordinary read-only reviewers can only propose candidates. Both
heldout arms use the same saved identity, standing instructions, source, contract,
prompt and effective tool grant. The control temporarily hides accepted Memory
while its child runs; the original is restored after confirmed closure. Each arm
uses a new parent history partition. Finding scores measure retention-assisted review,
not a general model-quality advantage. One run cannot establish statistical
benefit, especially when the control already finds every bug.

Inspect `metadata.json`, `study.json`, `receipts.json`, `spawns.json`, native
`child-*.jsonl` tool logs, `agents/` and `summary.json`. Report unanswered/failed
arms as missing coverage. Confirm full capability-body read results, rather than
counting index injection as retrieval. A proposal is never an accepted entry.
