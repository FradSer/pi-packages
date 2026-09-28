"""Worker extensions and capability tools are contributed by the caller.

Contract: packages/subagents/features/spawn-extension-contribution.feature

The spawner used to hardcode both: a `WORKER_EXTENSION` constant pointing at its
own package's index.ts, and a capability set naming `agent_event` and `work` —
tools registered by a different package. That is what would have made the
subagents / task / agent-teams split impossible: the execution layer would have
loaded another package's worker extension and granted two tools it does not
register.

These tests use deliberately neutral capability names (`alpha_tool`, `beta_tool`)
rather than the real coordination pair, because the property under test is that
the spawner is agnostic. The agent-teams suite asserts what that package actually
contributes.

The command line is read from inside a spawned child that dumps its own
`process.argv`, so these prove what the child was launched with rather than what
a builder function returned.
"""

from __future__ import annotations

import json

from subagents_helpers import PACKAGE, run_node, source

SPAWNER = (PACKAGE / "src" / "spawner.ts").as_uri()

FIRST_EXTENSION = "/tmp/first-worker.ts"
SECOND_EXTENSION = "/tmp/second-worker.ts"
CAPABILITY_TOOLS = '["alpha_tool", "beta_tool"]'


def spawn_with_argv_probe(extra_options: str) -> dict[str, object]:
    """Spawn a fake Pi CLI that reports the arguments it was launched with."""
    return run_node(
        f'''\
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "subagents-spawn-args-"));
        const pkg = path.join(root, "fake-package");
        fs.mkdirSync(pkg);
        fs.writeFileSync(path.join(pkg, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const child = path.join(pkg, "cli.mjs");
        fs.writeFileSync(child, `
          process.stderr.write("ARGVJSON" + JSON.stringify(process.argv.slice(2)) + "ARGVEND");
          process.exit(0);
        `, {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = child;
        const {{ spawnResident }} = await import("{SPAWNER}");
        const outcome = await new Promise((resolve) => {{
          const started = spawnResident({{
            workerName: "argv-probe",
            cwd: root,
            description: "probe",
            {extra_options}
            onUpdate: () => {{}},
            onExit: (result) => resolve({{ exitCode: result.exitCode, stderr: result.stderr }}),
            onError: (error) => resolve({{ error: error.message }}),
          }});
          // A refused spawn starts no child, so no exit or error callback fires.
          if ("error" in started) resolve({{ spawnError: started.error }});
        }});
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        console.log(JSON.stringify(outcome));
        '''
    )


def child_argv(payload: dict[str, object]) -> list[str]:
    stderr = str(payload["stderr"])
    assert "ARGVJSON" in stderr, f"the child did not report its arguments: {stderr[:200]}"
    begin = stderr.index("ARGVJSON") + len("ARGVJSON")
    end = stderr.index("ARGVEND")
    return json.loads(stderr[begin:end])


def flags_of(argv: list[str], flag: str) -> list[str]:
    return [argv[index + 1] for index, item in enumerate(argv) if item == flag and index + 1 < len(argv)]


# ── Rule: each contributing package supplies its own worker extension ──


def test_every_supplied_extension_reaches_the_child_command_line() -> None:
    payload = spawn_with_argv_probe(
        f'extensions: ["{FIRST_EXTENSION}", "{SECOND_EXTENSION}"],'
        f"capabilityTools: {CAPABILITY_TOOLS},"
    )
    argv = child_argv(payload)
    assert flags_of(argv, "--extension") == [FIRST_EXTENSION, SECOND_EXTENSION], (
        "each contributed extension needs its own --extension; -e is repeatable"
    )
    assert "--no-extensions" in argv, "discovered extensions must stay disabled"
    # No role grant was supplied, so the allowlist is exactly the contributed set.
    assert flags_of(argv, "--tools") == ["alpha_tool,beta_tool"]


def test_a_bare_child_carries_no_extension_and_only_the_role_grant() -> None:
    payload = spawn_with_argv_probe('tools: ["read", "bash"],')
    argv = child_argv(payload)
    assert "--extension" not in argv, "a spawn contributing nothing must load no worker extension"
    assert "--no-extensions" in argv
    assert flags_of(argv, "--tools") == ["read,bash"], (
        "with no contributed capability set the allowlist is exactly the role's grant"
    )


# ── Rule: a declared capability must have something to register it ──


def test_capability_tools_without_an_extension_are_refused() -> None:
    payload = spawn_with_argv_probe(f"capabilityTools: {CAPABILITY_TOOLS},")
    error = str(payload.get("spawnError", ""))
    assert "alpha_tool" in error and "no worker extension" in error, error
    # A refused spawn must not start a child at all.
    assert "stderr" not in payload, "no child process may be started for a refused spawn"
    assert "exitCode" not in payload


def test_the_spawner_hardcodes_no_extension_path_or_capability_tool_names() -> None:
    """The coupling that would have blocked the split must not come back."""
    spawner = source("spawner.ts")
    assert "WORKER_EXTENSION" not in spawner, "the spawner must not resolve its own package's worker entry"
    assert "import.meta.url" not in spawner, "the spawner must not derive an extension path from itself"
    assert "agent_event" not in spawner, "the spawner must not name another package's tool"
    assert '"work"' not in spawner, "the spawner must not name another package's tool"
    assert "capabilityTools" in spawner, "the contributed set must be a parameter, not a constant"


# ── Rule: a contributed set widens the grant and the universe ──


def test_a_contributed_capability_set_widens_the_grant_and_the_universe() -> None:
    payload = run_node(
        f'''\
        import {{ resolveWorkerTools, unknownWorkerTools, workerToolUniverse }} from "{SPAWNER}";
        const contributed = ["alpha_tool", "beta_tool"];
        console.log(JSON.stringify({{
          withCapability: resolveWorkerTools(["read", "alpha_tool"], contributed),
          bare: resolveWorkerTools(["read"], []),
          emptyRole: resolveWorkerTools([], contributed),
          undefinedRole: resolveWorkerTools(undefined, contributed),
          unknownWithCapability: unknownWorkerTools(["read", "mcp__x"], contributed),
          unknownBare: unknownWorkerTools(["alpha_tool", "read"], []),
          universeHasCapability: workerToolUniverse(contributed).includes("alpha_tool"),
          universeBare: workerToolUniverse([]).includes("alpha_tool"),
          universeHasBuiltins: workerToolUniverse([]).includes("read"),
        }}));
        '''
    )
    # The role's own listing of a capability id is deduplicated, not doubled.
    assert payload["withCapability"] == ["read", "alpha_tool", "beta_tool"]
    assert payload["bare"] == ["read"], "nothing is contributed, nothing is appended"
    assert payload["emptyRole"] == ["alpha_tool", "beta_tool"]
    assert payload["undefinedRole"] == ["alpha_tool", "beta_tool"]
    assert payload["unknownWithCapability"] == ["mcp__x"], "an MCP id can never reach a bare child"
    assert payload["unknownBare"] == ["alpha_tool"], (
        "with nothing contributed, a capability id is correctly ungrantable"
    )
    assert payload["universeHasCapability"] is True
    assert payload["universeBare"] is False
    assert payload["universeHasBuiltins"] is True, "pi built-ins stay grantable with no contribution"
