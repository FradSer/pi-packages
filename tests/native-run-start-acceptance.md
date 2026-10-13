# Native run-start acceptance

Run `tests/live_native_run_start.py` when verifying structured contributions through the actual Pi 1.2 print provider boundary.

```sh
mkdir -p /tmp/pi-native-run-start-evidence
PI_12_PACKAGE_DIR="$PI_PACKAGE_DIRECTORY" PI_12_BIN="$PI_CLI_FILE" \
  uv run --no-project python tests/live_native_run_start.py /tmp/pi-native-run-start-evidence
```

Both variables are required. The runner checks the package and CLI version against `1.2.0`.
The CLI variable accepts an executable or its `dist/cli.js` file.
No installation path is embedded in the test files.

## Contract

- Load actual Goal, Continual Learning, Context, Matt Pocock, and Monitor entry points.
- Use isolated HOME, agent configuration, project files, and a deterministic in-process provider.
- Disable automatic learning, Jev, unrelated resources, and built-in MCP.
- Refuse Node network transport and record rejected attempts.
- Capture complete JSON-encoded provider context and the current reconstructed system prompt for every request.
- Make three model requests and two actual read calls in each accepted run.
- Check all six structured sections once per request, including Memory and Harness.
- Check escaped malicious Memory descriptions, absent Memory bodies, and absent runtime blocks in user messages.
- Preserve fixture bytes and verify runtime source hashes after acceptance.

The custom case first runs an actual user prompt to establish retained Harness text-rule scope.
It then invokes a fixture command that sends one intentional custom trigger and waits for idle.
That trigger does not inject Memory, Harness, or other runtime instructions.
Pi encodes this trigger as a user message at the provider boundary.
The observer does not modify prompt options or return a complete system prompt.

## Latest result

Both cases pass with the configured installed Pi 1.2.0 CLI.
Evidence directory: `/private/tmp/pi-native-run-start-evidence/native-run-start-ou_27nj0`.
Inspect `manifest.json` and each case's `provider.jsonl`, `command.json`, `stdout.txt`, and `stderr.txt`.
Python compilation and scoped `git diff --check` pass.

Earlier attempts remain under the same evidence parent.
The first attempt incorrectly expected Memory names in discovery; the product exposes filename and description cues.
The second attempt returned from the custom command before its triggered run settled.
The third attempt expected Harness scope without a prior matching user prompt.
A later assertion incorrectly treated Pi's intentional custom trigger encoding as an injected user runtime block.
These fixture errors were corrected without production changes.

## Limits

This proves native print lifecycle and provider context composition only.
It does not prove TUI behavior, semantic adoption, real-model benefit, or Harness enforcement.
It does not verify an active Goal or an active Matt Pocock workflow.
No private data, user settings, paid model calls, or real Memory mutations are used.
The network check blocks Node transport; it is not an operating-system packet capture.
