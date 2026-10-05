# Real GitHub project learning experiment

Run explicitly from the repository root:

```sh
uv run --no-project packages/continual-learning/tests/live_docker_projects.py --jobs 3
```

This calls the configured real model and downloads public dependencies. It is
not collected by pytest. Use `--project click`, `--project p-limit`, or
`--project mitt` for one case, and `--output /absolute/new/directory` to choose
the artifact destination. The default destination is
`~/.cache/pi-continual-learning/docker/<UTC timestamp>/`.

The runner pins GitHub commits, builds Pi 1.0.2 with the current local plugin,
and starts one non-root Linux container per project. Containers have no host
filesystem or Docker socket mounts. Each starts with empty Memory, automatic
learning enabled, and AGENTS.md learning disabled. The actual task adds tests to
real project code, then independent checks verify the result. Later new sessions
must read complete learned entries, run the saved test command, and use the
private reporting preference. Safe Memory mirrors must match byte-for-byte.

The no-push check uses the native Pi Bash interception hook and an actual model
tool call. A local `git push` wrapper writes a marker if execution reaches it;
it cannot publish remotely. Verification requires the paired native error to
match an enabled learned block rule, an absent execution marker, and a separate
successful allowed command. Exact target commands and bounded working-directory
or stderr-redirection variants are accepted; echoes and arbitrary wrappers are
not execution evidence.

The configured OpenAI-compatible inference provider is reached through a
temporary host proxy. Real host authentication stays in the host process;
containers receive only a random short-lived proxy bearer. The proxy permits
only the chosen model and inference endpoints, with bounded requests, request
size, concurrency, and connection time. Literal/environment API keys are
supported; shell-command authentication and OAuth are outside this harness.

Click needs `less` for its upstream pager tests. The historical mitt checkout
needs npm-compatible hoisting, Node 18 types for TypeScript 4.9, generated bundles,
and a ts-node CommonJS test loader in place of obsolete `esm`. Only its disposable
checkout is adapted; all original typecheck, lint, Mocha and type-test stages
remain. The environment patch is exported separately. Production project source
is changed only if the model's regression exposes an actual defect.

Reports retain exact commits, source hashes, image IDs, native sessions, project
diffs, independent checks, receipts, and comparison counts. Failed stages and
artifact-transfer errors remain failures, including nonzero container exits.
Owned containers are removed after artifact export. The baseline uses a separate
empty agent configuration on the same filesystem: it may discover saved Memory
manually and succeed. A baseline success is not treated as an experiment failure.

See [the measured report](REPORT.md) for outcomes and limits.
