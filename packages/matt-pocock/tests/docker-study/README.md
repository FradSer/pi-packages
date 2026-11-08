# Compact hy4-dev Docker smoke

Run only when real-model execution is explicitly requested:

```sh
uv run --python 3.13 packages/matt-pocock/tests/docker-study/minimal.py --output /tmp/matt-minimal
```

This builds an image from the current `matt-pocock`, `kit` and root manifests
with Pi 1.5.0, then uses Magpie `hunyuan-eval/hy4-dev` through a host-only
transparent proxy. Every request sends `reasoning_effort: none`. The container
receives only a one-run `STUDY_PROXY_TOKEN`; the real `MAGPIE_API_KEY` and the
user's `~/.pi/agent` never enter the image or evidence.

Read `../../features/real-model-minimal-token.feature` for the scenario.
`native.ts` invokes the production extension's registered command and tools
directly, once per functional path: workflow command start and persisted state,
session restore, legal transition, no-UI decision, completion, gateway
`capability`, `user-capability`, `reference` and invalid crossover, workflow
reference load, command cancellation and unknown-token routing. `parent.py`
then lets the actual parent model select `matt_pocock_workflow` through native
Pi tool validation and exercises Ctrl+O expansion plus a 48-column repaint in
a real PTY. There is no provider stub: both requests reach hy4-dev.

Inspect `summary.json`, `metadata.json`, `native.json`, `native.log`,
`parent-tui.json` and both terminal captures. The summary reports request
count, wire reasoning state, resolved-procedure bytes and each contract check.
This is compact execution coverage, not a model-authored procedure journey,
review-quality measurement, statistical benefit claim or a replacement for the
29-case `tests/real_model_live.py` quality suite.
