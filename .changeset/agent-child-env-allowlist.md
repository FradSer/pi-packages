---
"@fradser/pi-agent-teams": minor
---

A spawned Agent child no longer inherits the leader's complete environment.

`spawnResident` used to launch the child with `{ ...process.env, ...options.env }`, so every Agent received every variable the developer had exported — provider keys, cloud credentials, personal encryption keys, registry auth tokens. One `env` call inside a child granted `bash` dumped all of them, and they propagated into every subprocess that child spawned and every crash report it produced.

**What changed**

- `src/child-env.ts` resolves the child environment from an explicit allowlist instead of the leader's whole environment: runtime and locale, editor/pager, Git and `SSH_AUTH_SOCK`, proxy and trust anchors, Node and language toolchain locations, and the Pi process markers and configuration variables. Names are matched exactly; the single admitted prefix is `LC_`.
- `PI_CODING_AGENT_DIR` passes through, which is what lets the child resolve the same `auth.json` and `models.json` as the leader. Pi stores OAuth credentials in `auth.json` and reads a literal or `$NAME`-interpolated `apiKey` from `models.json`, so a child needs the config directory rather than the parent's credential set.
- `PI_TEAMMATE_ENV_ALLOW` opts additional variables back in by exact name, comma-separated. Opting in a credential-shaped name works and is reported, so an operator's widening is visible rather than silent. A name the leader does not have is reported as missing instead of materialized as an empty placeholder.
- Spawn overrides remain authoritative over both the allowlist and the leader environment, and an override with an `undefined` value removes the name instead of passing the literal string `"undefined"`.
- The allowlist variable itself does not travel to the child, so a child that spawns in turn reaches its own strict default rather than inheriting a widening of its parent's.

**Observability**

The withheld count, the credential-shaped names, and the recovery instruction are recorded on the teammate and shown in the `/agent-teams` detail view. Per ADR-0002 this stays passive console telemetry and never wakes the leader. Names that embed a private URL — npm's `npm_config_//registry.example.com/:_authToken` shape — are redacted to a recognizable prefix, and no withheld value is ever rendered.

**Scope of the guarantee**

This is defense in depth against accidental leakage, not a containment boundary. A child granted `bash` can still read `~/.pi/agent/auth.json`, `~/.aws/credentials`, or a project `.env` directly from disk. Kernel write and read confinement is the sandbox-profile layer and is not part of this change.

**Migration**

A setup whose provider resolves credentials through environment interpolation now needs those exact names in `PI_TEAMMATE_ENV_ALLOW`. Nothing else changes: literal and OAuth configurations are unaffected because they resolve from the config directory.

Contract: `features/spawn-env-policy.feature`.

**Verification**

- `tests/test_child_env.py` covers the policy directly (16 tests), and
  `test_spawned_child_environment_is_the_policy_output` proves the wiring by
  spawning a real child that dumps its own `process.env` to stderr. A resolved
  environment that is not the environment the child receives would prove
  nothing, so the assertion is made from inside the child. macOS blocks
  `ps eww` environment inspection (it returns the header only), which is why the
  probe reads from inside.
- That integration test asserts the precise property, not a spot check: every
  name the child received must be allowlisted, supplied by that spawn, or
  declared runtime-injected; strictly fewer leader variables reach the child than
  the leader exports; and the reported `withheldCount` equals that difference
  exactly.
- `tests/live-child-env.ts` is the opt-in counterpart (`LIVE_AGENT_WORK_MODEL`):
  one real resident, one real model turn, confirming the allowlist did not remove
  anything the provider needs. On the reference machine it withheld **115**
  leader variables, **45** of them credential-shaped, and the child still
  completed its turn.
- `tests/test_teammate_package.py::test_resident_unterminated_output_is_terminated_without_partial_success`
  had to change. It configured its fake child through the leader's ambient
  `PI_LINE_LIMIT`, which the policy now withholds — a test that depended on the
  leak. It passes its knob through the spawn's own `overrides` instead, which is
  authoritative by design. The production allowlist was deliberately not widened
  to satisfy it.

**Hardening applied after self-review**

- `withheldSecretNames` is bounded to 16 **at the source** and
  `withheldSecretCount` carries the true total. It was previously unbounded in
  the persisted state, with the diagnostic and the console each applying their
  own cap — so a shell exporting many tokens could grow `envPolicy` on disk and
  the two surfaces could disagree.
- `RUNTIME_INJECTED_ENV_NAMES` declares `__CF_USER_TEXT_ENCODING`. libuv adds it
  to every macOS child regardless of the supplied environment, so no allowlist
  can withhold it; its value is a UID-derived locale hint, not a credential.
  Declaring it lets the test assert against an explicit narrow set instead of
  excusing any unexpected name, so a genuine leak cannot hide behind "the runtime
  probably added it". A name can be withheld by the policy and still present in
  the child this way; the withheld count reflects the policy's decision and is
  not reduced by the runtime putting the name back.
- `isAllowedEnvName` is exported for that subset assertion.
- The static tripwire tightened from `"...process.env" not in spawner` to
  `"process.env" not in spawner`. The weaker spelling would have passed on
  `Object.assign({}, process.env)`. The spawner now never reads the ambient
  environment directly; `child-env.ts` is its only reader.
- The `ALLOWED_EXACT` header now states that "non-secret" is not "inert":
  `NODE_OPTIONS`, `NODE_PATH`, `GIT_SSH_COMMAND`, `GIT_CONFIG_GLOBAL`, `EDITOR`,
  `VISUAL`, `PAGER`, `GIT_EDITOR`, `GIT_PAGER`, `SSL_CERT_FILE`, and
  `SSL_CERT_DIR` cause code execution or credential redirection in the child.
  They stay allowlisted because they originate in the developer's own shell and
  are not model-controllable, and because a child granted `bash` can already run
  arbitrary code. None carries a credential value, which is what this policy
  removes.
- `writeRoster` was verified to project only seven fields, so `envPolicy` never
  reaches the worker-readable roster file. It is persisted only in the
  leader-owned forensics state file, as names and counts, never values.
