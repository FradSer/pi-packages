# Compact hy4-dev Docker smoke

Run only when real-model execution is explicitly requested:

```sh
uv run --python 3.13 packages/monitor/tests/docker-study/minimal.py --output /tmp/monitor-minimal
```

This builds an image from the current `monitor`, `kit` and root manifests with
Pi 1.5.0, then uses Magpie `hunyuan-eval/hy4-dev` through a host-only
transparent proxy. Every request sends `reasoning_effort: none`. The container
receives only a one-run `STUDY_PROXY_TOKEN`; the real `MAGPIE_API_KEY` and the
user's `~/.pi/agent` never enter the image or evidence.

Read `../../features/real-model-minimal-token.feature` for the scenario.
`native.ts` invokes the production extension's registered tools, once per
functional path: headless match success, exit-mode JSON capture, failure
pattern precedence, `result_missing` on natural zero exit, bounded timeout,
UI-only asynchronous delivery, exact-id stop, unknown-id refusal,
capability-dependent prompt guidance, active-tool disclosure flips and
shutdown cleanup. `parent.py` then lets the actual parent model select
`monitor_start` through native Pi tool validation and exercises Ctrl+O
expansion plus a 48-column repaint in a real PTY. Both real requests reach
hy4-dev; no provider replies are stubbed.

Inspect `summary.json`, `metadata.json`, `native.json`, `native.log`,
`parent-tui.json` and both terminal captures. The summary reports request
count, wire reasoning state, model-facing bytes and each contract check.
This is compact execution coverage, not a model-authored monitoring workflow,
quality measurement, statistical benefit claim or a replacement for
`tests/live_monitor.py` and the native offline fixtures.
