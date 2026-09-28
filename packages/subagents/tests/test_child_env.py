"""Spawn environment policy: an Agent child receives an explicit non-secret
environment instead of the leader's complete environment.

Contract: packages/agent-teams/features/spawn-env-policy.feature
"""

from __future__ import annotations

import json

from subagents_helpers import PACKAGE, run_node, source

MODULE = (PACKAGE / "src" / "child-env.ts").as_uri()
ALLOW_VAR = "PI_TEAMMATE_ENV_ALLOW"

# Distinctive sentinels: a leak is provable by searching child values for them.
FIGMA_TOKEN = "SENTINEL-figma-7f3a9c"
CF_S3_KEY = "SENTINEL-cf-s3-4b2e81"
NOTE_KEY = "SENTINEL-note-enc-9d1c47"
NPM_AUTH = "SENTINEL-npm-auth-2e6b90"
ORDINARY = "SENTINEL-ordinary-value"


def resolve(
    parent_env: dict[str, str],
    overrides: dict[str, str] | None = None,
    allow: str | None = None,
) -> dict[str, object]:
    """Resolve one child environment from a fully synthetic leader environment."""
    env = dict(parent_env)
    if allow is not None:
        env[ALLOW_VAR] = allow
    return run_node(
        f'''\
        import {{ resolveChildEnv }} from "{MODULE}";
        const result = resolveChildEnv({{
          parentEnv: {json.dumps(env)},
          overrides: {json.dumps(overrides or {})},
          allowVar: {json.dumps(ALLOW_VAR)},
        }});
        console.log(JSON.stringify({{
          env: result.env,
          withheldCount: result.withheldCount,
          withheldSecretCount: result.withheldSecretCount,
          withheldSecretNames: result.withheldSecretNames,
          missingAllowed: result.missingAllowed,
          flaggedAllowOverrides: result.flaggedAllowOverrides,
          diagnostic: result.diagnostic,
        }}));
        '''
    )


def secret_leader_env() -> dict[str, str]:
    """A leader environment shaped like a real developer shell."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/home/dev",
        "LANG": "en_US.UTF-8",
        "PI_CODING_AGENT_DIR": "/home/dev/.pi/agent",
        "HTTPS_PROXY": "http://127.0.0.1:7890",
        "NO_PROXY": "localhost",
        "SSH_AUTH_SOCK": "/tmp/ssh-XYZ/agent.1",
        "FIGMA_TOKEN": FIGMA_TOKEN,
        "CF_S3_KEY": CF_S3_KEY,
        "NOTE_ENCRYPTION_KEY": NOTE_KEY,
        "npm_config_//registry.corp.example.com/:_authToken": NPM_AUTH,
        "EDITOR": "vim",
        "ORDINARY_BUILD_FLAG": ORDINARY,
    }


# ── Rule: the child receives what it needs to run and authenticate ──


def test_runtime_essentials_pass_through() -> None:
    env = resolve(secret_leader_env())["env"]
    assert isinstance(env, dict)
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOME"] == "/home/dev"
    assert env["LANG"] == "en_US.UTF-8"


def test_pi_configuration_reaches_the_child() -> None:
    env = resolve(secret_leader_env())["env"]
    assert isinstance(env, dict)
    # Without this the child resolves a different config directory and cannot
    # read the auth.json / models.json that hold its provider credentials.
    assert env["PI_CODING_AGENT_DIR"] == "/home/dev/.pi/agent"


def test_proxy_and_ssh_agent_pass_through() -> None:
    env = resolve(secret_leader_env())["env"]
    assert isinstance(env, dict)
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert env["NO_PROXY"] == "localhost"
    assert env["SSH_AUTH_SOCK"] == "/tmp/ssh-XYZ/agent.1"


# ── Rule: secrets are withheld by default ──


def test_unrelated_credentials_are_withheld() -> None:
    result = resolve(secret_leader_env())
    env = result["env"]
    assert isinstance(env, dict)
    for name in ("FIGMA_TOKEN", "CF_S3_KEY", "NOTE_ENCRYPTION_KEY"):
        assert name not in env, name
    values = [str(value) for value in env.values() if value is not None]
    for secret in (FIGMA_TOKEN, CF_S3_KEY, NOTE_KEY):
        assert secret not in values, "a withheld value reached the child"


def test_credential_name_embedding_a_private_url_is_withheld_and_not_echoed() -> None:
    result = resolve(secret_leader_env())
    env = result["env"]
    assert isinstance(env, dict)
    assert "npm_config_//registry.corp.example.com/:_authToken" not in env
    assert NPM_AUTH not in [str(v) for v in env.values() if v is not None]
    # The name itself embeds a private registry host; the diagnostic must not
    # reproduce it.
    names = result["withheldSecretNames"]
    assert isinstance(names, list)
    diagnostic = str(result["diagnostic"])
    for text in (*names, diagnostic):
        assert "registry.corp.example.com" not in str(text)


# ── Rule: withholding is observable and reversible, never silent ──


def test_resolution_reports_withheld_names_without_revealing_values() -> None:
    result = resolve(secret_leader_env())
    names = result["withheldSecretNames"]
    assert isinstance(names, list)
    assert set(names) >= {"FIGMA_TOKEN", "CF_S3_KEY", "NOTE_ENCRYPTION_KEY"}
    count = result["withheldCount"]
    assert isinstance(count, int)
    # Everything outside the allowlist counts as withheld, secrets or not.
    assert count >= 4
    diagnostic = str(result["diagnostic"])
    assert ALLOW_VAR in diagnostic, "the diagnostic must name the recovery path"
    for secret in (FIGMA_TOKEN, CF_S3_KEY, NOTE_KEY, NPM_AUTH, ORDINARY):
        assert secret not in diagnostic


def test_operator_opts_one_variable_back_in_by_exact_name() -> None:
    result = resolve(secret_leader_env(), allow="FIGMA_TOKEN")
    env = result["env"]
    assert isinstance(env, dict)
    assert env["FIGMA_TOKEN"] == FIGMA_TOKEN
    # Opting one name in does not widen the rest.
    assert "CF_S3_KEY" not in env


def test_a_requested_name_the_leader_lacks_is_reported_not_invented() -> None:
    result = resolve(secret_leader_env(), allow="ABSENT_PROVIDER_KEY")
    env = result["env"]
    assert isinstance(env, dict)
    assert "ABSENT_PROVIDER_KEY" not in env
    missing = result["missingAllowed"]
    assert isinstance(missing, list)
    assert missing == ["ABSENT_PROVIDER_KEY"]


def test_opting_in_a_secret_bearing_name_is_allowed_but_flagged() -> None:
    result = resolve(secret_leader_env(), allow="CF_S3_KEY")
    env = result["env"]
    assert isinstance(env, dict)
    assert env["CF_S3_KEY"] == CF_S3_KEY
    flagged = result["flaggedAllowOverrides"]
    assert isinstance(flagged, list)
    assert flagged == ["CF_S3_KEY"]


# ── Rule: spawner overrides are authoritative ──


def test_spawner_overrides_always_win() -> None:
    overrides = {
        "PI_TEAMMATE_WORKER_NAME": "reviewer",
        "PI_TEAMMATE_SPAWN_ID": "spawn-1",
        "PI_TEAMMATE_OUTBOX_FILE": "/tmp/outbox.jsonl",
    }
    env = resolve(secret_leader_env(), overrides=overrides)["env"]
    assert isinstance(env, dict)
    for name, value in overrides.items():
        assert env[name] == value, name


def test_an_override_replaces_the_leader_value() -> None:
    leader = dict(secret_leader_env())
    leader["PI_TEAMMATE_SPAWN_ID"] = "stale-from-leader"
    env = resolve(leader, overrides={"PI_TEAMMATE_SPAWN_ID": "spawn-2"})["env"]
    assert isinstance(env, dict)
    assert env["PI_TEAMMATE_SPAWN_ID"] == "spawn-2"


# ── Regression guard on the spawn site itself ──


def test_spawner_does_not_inherit_the_complete_leader_environment() -> None:
    """The original defect: the child was spawned with the leader's whole env.

    Asserted as the strong invariant rather than one spelling of the leak. The
    spawner must never touch the ambient environment at all; the only legitimate
    reader of `process.env` is child-env.ts, where it is the documented default
    parent environment for the policy. A check for `...process.env` alone would
    still pass on `Object.assign({}, process.env)`.
    """
    spawner = source("spawner.ts")
    assert "process.env" not in spawner, (
        "spawner.ts reads the ambient environment directly; it must resolve the "
        "child environment through child-env.ts and nothing else"
    )
    assert "resolveChildEnv" in spawner, "spawner.ts must resolve the child env through the policy"
    assert source("child-env.ts"), "child-env.ts is missing"


def test_withheld_secret_names_are_bounded_at_the_source() -> None:
    """A shell exporting a hundred tokens must not grow the persisted state.

    The bound lives in resolveChildEnv, so the diagnostic and the console render
    the same list instead of each applying its own cap.
    """
    parent = {f"VENDOR_{index:03d}_TOKEN": f"value-{index}" for index in range(40)}
    parent["PATH"] = "/usr/bin"
    result = resolve(parent)
    names = result["withheldSecretNames"]
    assert isinstance(names, list)
    assert len(names) == 16, "the name list must be bounded once, at the source"
    assert result["withheldSecretCount"] == 40, "the true total must survive the bound"
    assert result["withheldCount"] == 40
    assert "24 more" in str(result["diagnostic"]), "the diagnostic must report the truncated remainder"


def test_an_allowlisted_credential_adjacent_name_is_not_counted_withheld() -> None:
    """The counts describe withheld variables only.

    SSH_AUTH_SOCK is credential-adjacent by name but allowlisted, so it must
    reach the child and must not inflate the withheld counts.
    """
    result = resolve({"PATH": "/usr/bin", "SSH_AUTH_SOCK": "/tmp/agent.1"})
    env = result["env"]
    assert isinstance(env, dict)
    assert env["SSH_AUTH_SOCK"] == "/tmp/agent.1"
    assert result["withheldCount"] == 0
    assert result["withheldSecretCount"] == 0


def test_a_runtime_injected_name_the_leader_exports_still_counts_as_withheld() -> None:
    """The policy withholds it; the platform then puts it back.

    `__CF_USER_TEXT_ENCODING` is not allowlisted, so resolveChildEnv withholds it
    even though libuv re-adds it to every macOS child. Both facts are true at
    once, and the withheld count must reflect the policy's decision rather than
    the child's final environment. Pinned deterministically here because the
    integration test's arithmetic depends on whether the host happens to export
    the name.
    """
    result = resolve({"PATH": "/usr/bin", "__CF_USER_TEXT_ENCODING": "0x0:0x0"})
    env = result["env"]
    assert isinstance(env, dict)
    assert "__CF_USER_TEXT_ENCODING" not in env, "the policy must not pass it through"
    assert result["withheldCount"] == 1
    # Not credential-bearing by name, so it is withheld but not named as a secret.
    assert result["withheldSecretCount"] == 0
    assert result["withheldSecretNames"] == []


# ── Integration: the real spawn path, verified from inside the child ──
#
# The unit tests above prove what the policy returns. This proves the spawner
# actually hands that result to the child process. The child is a fake Pi CLI
# that dumps its own environment to stderr, so the assertion is made against the
# real OS-level environment of a real spawned process rather than against a
# model's report of it. macOS blocks `ps eww` environment inspection, so reading
# the child's environment from outside is not available; reading it from inside
# is both portable and stronger.

SPAWN_SENTINEL_NAME = "AGENT_TEAMS_LEAK_SENTINEL_TOKEN"
SPAWN_SENTINEL_VALUE = "SENTINEL-leak-4c81ab"
SPAWN_ALLOWED_MARKER = "SENTINEL-allowed-editor"


def test_spawned_child_environment_is_the_policy_output() -> None:
    payload = run_node(
        f'''\
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        const root = fs.mkdtempSync(path.join(os.tmpdir(), "agent-teams-child-env-"));
        const pkg = path.join(root, "fake-package");
        fs.mkdirSync(pkg);
        fs.writeFileSync(path.join(pkg, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const child = path.join(pkg, "cli.mjs");
        fs.writeFileSync(child, `
          process.stderr.write("ENVJSON" + JSON.stringify(process.env) + "ENVEND");
          process.exit(0);
        `, {{ mode: 0o755 }});
        const originalArgv1 = process.argv[1];
        process.argv[1] = child;
        process.env["{SPAWN_SENTINEL_NAME}"] = "{SPAWN_SENTINEL_VALUE}";
        process.env.EDITOR = "{SPAWN_ALLOWED_MARKER}";
        const {{ spawnResident }} = await import("{(PACKAGE / "src" / "spawner.ts").as_uri()}");
        const {{ isAllowedEnvName, isSecretBearingName, RUNTIME_INJECTED_ENV_NAMES }} = await import("{(PACKAGE / "src" / "child-env.ts").as_uri()}");
        const overrides = {{ PI_TEAMMATE_SPAWN_ID: "spawn-probe" }};
        const leaderKeyCount = Object.keys(process.env).length;
        let envPolicy;
        const outcome = await new Promise((resolve) => {{
          const started = spawnResident({{
            workerName: "env-probe",
            cwd: root,
            description: "probe",
            // The fake CLI ignores its arguments, so no worker extension is
            // loaded; the policy is what this test exercises.
            extensions: [],
            env: overrides,
            onUpdate: () => {{}},
            onExit: (result) => resolve({{ exitCode: result.exitCode, stderr: result.stderr }}),
            onError: (error) => resolve({{ error: error.message }}),
          }});
          envPolicy = "error" in started ? {{ error: started.error }} : started.envPolicy;
        }});
        process.argv[1] = originalArgv1;
        fs.rmSync(root, {{ recursive: true, force: true }});
        const stderr = outcome.stderr ?? "";
        const begin = stderr.indexOf("ENVJSON");
        const end = stderr.indexOf("ENVEND");
        const childEnv = begin < 0 || end < 0 ? null : JSON.parse(stderr.slice(begin + 7, end));
        // The precise property: every name the child received was either admitted
        // by the allowlist, supplied by this spawn, or injected by the platform
        // runtime. Checking one sentinel would still pass if the allowlist
        // accidentally admitted a whole class.
        const keys = childEnv === null ? [] : Object.keys(childEnv);
        const unexpected = childEnv === null
          ? ["CHILD_ENV_UNREADABLE"]
          : keys.filter((name) => !isAllowedEnvName(name) && !(name in overrides)
              && !RUNTIME_INJECTED_ENV_NAMES.includes(name));
        const runtimeInjected = keys.filter((name) => RUNTIME_INJECTED_ENV_NAMES.includes(name));
        const injectedLookSecret = runtimeInjected.filter((name) => isSecretBearingName(name));
        // Names the policy passed through from the leader, for exact arithmetic.
        // A runtime-injected name is excluded even when the leader also exports
        // it: the policy withheld that name, and its presence in the child is the
        // runtime's doing, so counting it as passed would double-count it against
        // withheldCount.
        const passedFromLeader = keys.filter((name) => name in process.env
          && !RUNTIME_INJECTED_ENV_NAMES.includes(name));
        console.log(JSON.stringify({{
          exitCode: outcome.exitCode,
          error: outcome.error,
          envPolicy,
          childEnv,
          unexpected,
          runtimeInjected,
          injectedLookSecret,
          passedFromLeaderCount: passedFromLeader.length,
          leaderKeyCount,
        }}));
        '''
    )
    assert not payload.get("error"), payload.get("error")
    child_env = payload["childEnv"]
    assert isinstance(child_env, dict), f"the child did not report its environment: {child_env}"

    # The whole allowlist-or-override property, not one spot check.
    assert payload["unexpected"] == [], f"child received names outside the policy: {payload['unexpected']}"
    # The platform may add names the policy cannot withhold, but they must be the
    # declared ones and must not be credential-bearing.
    assert payload["injectedLookSecret"] == [], payload["injectedLookSecret"]
    for name in payload["runtimeInjected"]:
        assert str(name) != SPAWN_SENTINEL_NAME
        assert str(child_env.get(name)) != SPAWN_SENTINEL_VALUE
    # The sentinel is secret-shaped and not allowlisted: it must not have crossed.
    assert SPAWN_SENTINEL_NAME not in child_env
    assert SPAWN_SENTINEL_VALUE not in [str(v) for v in child_env.values()]
    # Allowlisted runtime and the spawner's own binding must have crossed.
    assert child_env.get("PATH"), "PATH must reach the child"
    assert child_env.get("HOME"), "HOME must reach the child"
    assert child_env.get("EDITOR") == SPAWN_ALLOWED_MARKER
    assert child_env.get("PI_TEAMMATE_SPAWN_ID") == "spawn-probe"
    # The policy must actually narrow the environment on a real developer shell.
    leader_keys = int(str(payload["leaderKeyCount"]))
    passed = int(str(payload["passedFromLeaderCount"]))
    assert passed < leader_keys, (
        f"child received {passed} of {leader_keys} leader variables; the policy narrowed nothing"
    )

    policy = payload["envPolicy"]
    assert isinstance(policy, dict), policy
    assert policy["withheldCount"] == leader_keys - passed, (
        f"withheld {policy['withheldCount']} but {leader_keys} leader variables minus "
        f"{passed} passed is {leader_keys - passed}"
    )
    assert policy["withheldCount"] >= 1
    assert int(str(policy["withheldSecretCount"])) >= 1
    assert SPAWN_SENTINEL_VALUE not in str(policy["diagnostic"])

    # The name list is bounded at the source, so on a shell exporting more than
    # the cap in credential-shaped variables the sentinel may legitimately be
    # truncated out. Truncation is the only acceptable reason for its absence:
    # an unbounded list must still name it. Asserted without printing the list,
    # which holds real variable names from the host environment.
    names = policy["withheldSecretNames"]
    assert isinstance(names, list)
    assert len(names) <= 16, "the name list must stay bounded"
    truncated = len(names) == 16
    assert (SPAWN_SENTINEL_NAME in names) or truncated, (
        f"sentinel absent from an untruncated withheld-name list ({len(names)} names)"
    )
    if truncated:
        assert "more" in str(policy["diagnostic"]), "a truncated list must report the remainder"
