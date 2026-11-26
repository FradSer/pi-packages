from __future__ import annotations

# --- Merged from test_child_env.py ---
# --- Merged from test_child_env.py ---
"""Spawn environment policy: an Agent child receives an explicit non-secret
environment instead of the leader's complete environment.

Contract: packages/agent-teams/features/spawn-env-policy.feature
"""


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


def test_runtime_configuration_proxy_and_ssh_pass_through() -> None:
    env = resolve(secret_leader_env())["env"]
    assert isinstance(env, dict)
    assert {key: env[key] for key in ("PATH", "HOME", "LANG", "PI_CODING_AGENT_DIR", "HTTPS_PROXY", "NO_PROXY", "SSH_AUTH_SOCK")} == {
        "PATH": "/usr/bin:/bin", "HOME": "/home/dev", "LANG": "en_US.UTF-8",
        "PI_CODING_AGENT_DIR": "/home/dev/.pi/agent", "HTTPS_PROXY": "http://127.0.0.1:7890",
        "NO_PROXY": "localhost", "SSH_AUTH_SOCK": "/tmp/ssh-XYZ/agent.1",
    }








# ── Rule: secrets are withheld by default ──


def test_the_leaders_session_directory_does_not_reach_the_child() -> None:
    """A session directory is the leader's own state, not configuration a child
    needs. Inheriting it writes every child turn into the leader's session store,
    which is the one outcome per-workspace session grouping exists to prevent —
    and the spawner passes no `--session-dir` to put it right. An operator who
    wants a child to share it can still name it, so nothing is taken away."""
    parent = {"PATH": "/usr/bin", "PI_CODING_AGENT_SESSION_DIR": "/leader/sessions"}
    withheld = resolve(parent)
    assert withheld["env"].get("PI_CODING_AGENT_SESSION_DIR") is None
    # Exactly one leader variable went missing, and PATH is allowlisted, so the
    # withheld one is the session directory rather than something incidental.
    assert withheld["withheldCount"] == 1
    opted_in = resolve(parent, allow="PI_CODING_AGENT_SESSION_DIR")
    assert opted_in["env"].get("PI_CODING_AGENT_SESSION_DIR") == "/leader/sessions"


def test_credential_filtering_and_value_free_diagnostics() -> None:
    result = resolve(secret_leader_env())
    env = result["env"]
    assert isinstance(env, dict)
    for name in ("FIGMA_TOKEN", "CF_S3_KEY", "NOTE_ENCRYPTION_KEY", "npm_config_//registry.corp.example.com/:_authToken"):
        assert name not in env, name
    values = [str(value) for value in env.values() if value is not None]
    for secret in (FIGMA_TOKEN, CF_S3_KEY, NOTE_KEY, NPM_AUTH):
        assert secret not in values, "a withheld value reached the child"
    names = result["withheldSecretNames"]
    assert set(names) >= {"FIGMA_TOKEN", "CF_S3_KEY", "NOTE_ENCRYPTION_KEY"}
    assert result["withheldCount"] >= 4
    diagnostic = str(result["diagnostic"])
    assert ALLOW_VAR in diagnostic
    for secret in (FIGMA_TOKEN, CF_S3_KEY, NOTE_KEY, NPM_AUTH, ORDINARY):
        assert secret not in diagnostic
    assert all("registry.corp.example.com" not in text for text in [*names, diagnostic])





# ── Rule: withholding is observable and reversible, never silent ──





def test_exact_opt_in_is_flagged_without_widening_other_names() -> None:
    result = resolve(secret_leader_env(), allow="FIGMA_TOKEN")
    env = result["env"]
    assert isinstance(env, dict)
    assert env["FIGMA_TOKEN"] == FIGMA_TOKEN
    # Opting one name in does not widen the rest.
    assert "CF_S3_KEY" not in env
    assert result["flaggedAllowOverrides"] == ["FIGMA_TOKEN"]


def test_a_requested_name_the_leader_lacks_is_reported_not_invented() -> None:
    result = resolve(secret_leader_env(), allow="ABSENT_PROVIDER_KEY")
    env = result["env"]
    assert isinstance(env, dict)
    assert "ABSENT_PROVIDER_KEY" not in env
    missing = result["missingAllowed"]
    assert isinstance(missing, list)
    assert missing == ["ABSENT_PROVIDER_KEY"]





# ── Rule: spawner overrides are authoritative ──


def test_spawner_overrides_always_win() -> None:
    overrides = {
        "PI_TEAMMATE_WORKER_NAME": "reviewer",
        "PI_TEAMMATE_SPAWN_ID": "spawn-1",
        "PI_TEAMMATE_OUTBOX_FILE": "/tmp/outbox.jsonl",
    }
    leader = {**secret_leader_env(), "PI_TEAMMATE_SPAWN_ID": "stale-from-leader"}
    env = resolve(leader, overrides=overrides)["env"]
    assert isinstance(env, dict)
    for name, value in overrides.items():
        assert env[name] == value, name





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
            agentName: "env-probe",
            cwd: root,
            description: "probe",
            // The fake CLI ignores its arguments, so no Agent extension is
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


# --- Merged from test_agent_workspace.py ---
"""Ordinary durable homes; VISION.md replaces the former Git-worktree policy.

Contract: features/agent-workspace.feature. Every process uses isolated HOME/config.
"""


import hashlib
import json
import re
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, run_node

WORKSPACE = (PACKAGE / "src" / "workspace.ts").as_uri()


def run(script: str, tmp_path: Path) -> dict[str, object]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return run_node(
        f'''import * as sa from {json.dumps(WORKSPACE)};
        import fs from "node:fs";
        import path from "node:path";
        const cwd = process.env.PI_TEST_CWD;
        {script}''',
        env_overrides={
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / "config"),
            "PI_CODING_AGENT_DIR": str(home / "agent"),
            "PI_TEST_CWD": str(project),
        },
    )


def test_paths_are_read_only_private_and_scoped(tmp_path: Path) -> None:
    result = run('''
      const home = sa.agentHomePath("reviewer");
      const workspace = sa.agentWorkspacePath("reviewer");
      const session = sa.agentSessionPath("reviewer", cwd);
      console.log(JSON.stringify({home, workspace, session,
        stable: sa.agentSessionPath("reviewer", cwd) === session,
        otherAgent: sa.agentHomePath("builder") !== home,
        otherProject: sa.agentSessionPath("reviewer", path.dirname(cwd)) !== session,
        created: fs.existsSync(process.env.PI_CODING_AGENT_DIR)}));
    ''', tmp_path)
    home = tmp_path / "home" / "agent" / "agents" / "reviewer"
    assert result["home"] == str(home)
    assert result["workspace"] == str(home / "workspace")
    slug = run('console.log(JSON.stringify({slug:sa.projectSlug(cwd)}));', tmp_path)["slug"]
    assert result["session"] == str(home / "projects" / str(slug) / "session")
    assert result["stable"] is True
    assert result["otherAgent"] is True and result["otherProject"] is True
    assert result["created"] is False


def test_parent_session_paths_are_hashed_stable_and_isolated(tmp_path: Path) -> None:
    result = run('''
      const first = sa.agentSessionPath("reviewer",cwd,"parent-one");
      const same = sa.agentSessionPath("reviewer",cwd,"parent-one");
      const other = sa.agentSessionPath("reviewer",cwd,"parent-two");
      const legacy = sa.agentSessionPath("reviewer",cwd);
      console.log(JSON.stringify({first,same,other,legacy,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}));
    ''', tmp_path)
    home = tmp_path / "home" / "agent" / "agents" / "reviewer"
    expected = f"parent-{hashlib.sha256(b'parent-one').hexdigest()}"
    other_expected = f"parent-{hashlib.sha256(b'parent-two').hexdigest()}"
    first = Path(str(result["first"]))
    other = Path(str(result["other"]))
    assert result["first"] == result["same"]
    assert result["first"] != result["other"]
    assert first == home / "projects" / first.parent.parent.parent.name / "parents" / expected / "session"
    assert other.parent.name == other_expected
    assert re.fullmatch(r"parent-[0-9a-f]{64}", first.parent.name)
    assert "parent-one" not in str(first) and "parent-two" not in str(other)
    assert result["legacy"] == str(home / "projects" / first.parent.parent.parent.name / "session")
    assert result["created"] is False


@pytest.mark.parametrize("parent_id", ["", "   ", "\t"])
def test_blank_parent_session_id_is_refused_before_writes(tmp_path: Path, parent_id: str) -> None:
    result = run(f'''
      const parentId = {json.dumps(parent_id)};
      const refused = [];
      for (const action of [
        () => sa.agentSessionPath("reviewer",cwd,parentId),
        () => sa.ensureAgentWorkspace({{agentName:"reviewer",cwd,parentSessionId:parentId}}),
      ]) {{
        try {{ action(); refused.push(false); }} catch {{ refused.push(true); }}
      }}
      console.log(JSON.stringify({{refused,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}}));
    ''', tmp_path)
    assert result == {"refused": [True, True], "created": False}


def test_oversized_parent_session_id_is_refused_before_writes(tmp_path: Path) -> None:
    result = run('''
      const parentId = "x".repeat(4097);
      let refused = false;
      try { sa.ensureAgentWorkspace({agentName:"reviewer",cwd,parentSessionId:parentId}); } catch { refused = true; }
      console.log(JSON.stringify({refused,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}));
    ''', tmp_path)
    assert result == {"refused": True, "created": False}


def test_new_parent_session_does_not_import_legacy_history(tmp_path: Path) -> None:
    result = run('''
      const legacy = sa.agentSessionPath("reviewer",cwd);
      fs.mkdirSync(legacy,{recursive:true});
      const oldFile = path.join(legacy,"history.jsonl");
      fs.writeFileSync(oldFile,"LEGACY_HISTORY\\n");
      const before = fs.readFileSync(oldFile);
      const provisioned = sa.ensureAgentWorkspace({agentName:"reviewer",cwd,parentSessionId:"new-parent"});
      console.log(JSON.stringify({
        legacy,session:provisioned.sessionDir,
        legacyExists:fs.existsSync(legacy),oldUnchanged:fs.readFileSync(oldFile).equals(before),
        newExists:fs.statSync(provisioned.sessionDir).isDirectory(),same:legacy===provisioned.sessionDir,
        oldEntries:fs.readdirSync(legacy),newEntries:fs.readdirSync(provisioned.sessionDir)
      }));
    ''', tmp_path)
    assert result["legacyExists"] is True and result["oldUnchanged"] is True
    assert result["same"] is False and result["newExists"] is True
    assert result["oldEntries"] == ["history.jsonl"]
    assert result["newEntries"] == []


@pytest.mark.parametrize("entry", ["symlink", "dangling", "directory", "hard-link"])
def test_provision_refuses_unsafe_jsonl_history_before_writes(tmp_path: Path, entry: str) -> None:
    result = run(f'''
      const session=sa.agentSessionPath("reviewer",cwd);fs.mkdirSync(session,{{recursive:true}});
      const outside=path.join(cwd,"outside-history.jsonl");fs.writeFileSync(outside,"private-history\\n");
      const before=fs.readFileSync(outside);const candidate=path.join(session,"unsafe.jsonl");
      const kind={json.dumps(entry)};
      if(kind==="symlink")fs.symlinkSync(outside,candidate);
      else if(kind==="dangling")fs.symlinkSync(path.join(cwd,"absent-history"),candidate);
      else if(kind==="hard-link")fs.linkSync(outside,candidate);
      else fs.mkdirSync(candidate);
      let error="";try{{sa.ensureAgentWorkspace({{agentName:"reviewer",cwd}});}}catch(e){{error=e.message;}}
      console.log(JSON.stringify({{error,unchanged:fs.readFileSync(outside).equals(before),
        state:fs.existsSync(path.join(sa.agentHomePath("reviewer"),"state.json")),
        memory:fs.existsSync(path.join(sa.agentHomePath("reviewer"),"memory"))}}));
    ''', tmp_path)
    assert result["error"]
    assert result["unchanged"] is True
    assert result["state"] is False and result["memory"] is False


def test_project_slug_preserves_the_existing_hash_algorithm(tmp_path: Path) -> None:
    result = run('console.log(JSON.stringify({slug:sa.projectSlug(cwd),cwd}));', tmp_path)
    resolved = str(Path(str(result["cwd"])).resolve())
    digest = hashlib.sha256(resolved.encode()).hexdigest()[:12]
    readable = resolved.lstrip("/").replace("/", "-")[-120:]
    assert result["slug"] == f"{readable}-{digest}"


def test_first_provision_creates_ordinary_dirs_and_second_reuses(tmp_path: Path) -> None:
    result = run('''
      const first = sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const second = sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const home = sa.agentHomePath("reviewer");
      console.log(JSON.stringify({first,second,
        index:fs.readFileSync(path.join(home,"memory","MEMORY.md"),"utf8"),
        proposals:fs.statSync(path.join(home,"memory","proposals")).isDirectory(),
        workspace:fs.statSync(first.workspacePath).isDirectory(),
        session:fs.statSync(first.sessionDir).isDirectory(),
        git:fs.existsSync(path.join(first.workspacePath,".git")),
        definition:fs.existsSync(path.join(home,"agent.md")),
        state:JSON.parse(fs.readFileSync(path.join(home,"state.json"),"utf8")),
        temp:fs.readdirSync(home).filter(n=>n.endsWith(".tmp"))}));
    ''', tmp_path)
    first, second = result["first"], result["second"]
    assert set(first) == {"cwd", "workspacePath", "sessionDir", "reused"}
    assert first["cwd"] == str(tmp_path / "project")
    assert first["cwd"] != first["workspacePath"]
    assert first["reused"] is False and second["reused"] is True
    assert first["workspacePath"] == second["workspacePath"]
    assert first["sessionDir"] == second["sessionDir"]
    assert "Agent Memory" in result["index"]
    assert result["proposals"] is True and result["workspace"] is True and result["session"] is True
    assert result["git"] is False and result["definition"] is False
    assert set(result["state"]) == {"createdAt", "lastProject", "memoryEntryCount"}
    assert result["state"]["lastProject"] == str(tmp_path / "project")
    assert result["state"]["memoryEntryCount"] == 0
    assert result["temp"] == []


def test_provision_preserves_index_output_and_creation_time(tmp_path: Path) -> None:
    result = run('''
      const first = sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const home = sa.agentHomePath("reviewer");
      const statePath = path.join(home,"state.json");
      const originalState = JSON.parse(fs.readFileSync(statePath,"utf8"));
      const indexPath = path.join(home,"memory","MEMORY.md");
      const index = "CUSTOM INDEX\\r\\n保留内容\\n";
      fs.writeFileSync(indexPath,index);
      fs.writeFileSync(path.join(home,"memory","lesson.md"),"entry");
      fs.writeFileSync(path.join(home,"memory","proposals","candidate.md"),"proposal");
      fs.writeFileSync(path.join(first.workspacePath,"output.bin"),Buffer.from([0,255,10]));
      const otherProject = path.join(cwd,"other");fs.mkdirSync(otherProject);
      const second = sa.ensureAgentWorkspace({agentName:"reviewer",cwd:otherProject});
      const state = JSON.parse(fs.readFileSync(statePath,"utf8"));
      console.log(JSON.stringify({state,otherProject,
        creationKept:state.createdAt===originalState.createdAt,
        indexKept:fs.readFileSync(indexPath,"utf8")===index,
        output:[...fs.readFileSync(path.join(first.workspacePath,"output.bin"))],
        sameScratch:first.workspacePath===second.workspacePath,
        distinctSession:first.sessionDir!==second.sessionDir,
        reused:second.reused,definition:fs.existsSync(path.join(home,"agent.md"))}));
    ''', tmp_path)
    assert result["creationKept"] is True and result["indexKept"] is True
    assert result["output"] == [0, 255, 10]
    assert result["sameScratch"] is True and result["distinctSession"] is True
    assert result["reused"] is True and result["definition"] is False
    assert result["state"]["lastProject"] == result["otherProject"]
    assert result["state"]["memoryEntryCount"] == 1


@pytest.mark.parametrize("name", ["../escape", "a/b", "a\\b", "", "..", "reviewer.local"])
def test_path_helpers_reject_unsafe_or_reserved_names(tmp_path: Path, name: str) -> None:
    result = run(f'''
      const refused = [];
      for (const f of [()=>sa.agentHomePath({json.dumps(name)}),()=>sa.agentWorkspacePath({json.dumps(name)}),
        ()=>sa.agentSessionPath({json.dumps(name)},cwd),()=>sa.ensureAgentWorkspace({{agentName:{json.dumps(name)},cwd}})]) {{
        try {{ f();refused.push(false); }} catch {{refused.push(true);}}
      }}
      console.log(JSON.stringify({{refused,created:fs.existsSync(process.env.PI_CODING_AGENT_DIR)}}));
    ''', tmp_path)
    assert result == {"refused": [True, True, True, True], "created": False}


@pytest.mark.parametrize("unsafe", ["home", "memory", "MEMORY.md", "workspace", "projects", "state.json"])
def test_provision_refuses_symlinks_without_changing_their_target(tmp_path: Path, unsafe: str) -> None:
    result = run(f'''
      const home = sa.agentHomePath("reviewer");
      const outside = path.join(cwd,"outside");fs.mkdirSync(outside);
      const sentinel = path.join(outside,"sentinel");fs.writeFileSync(sentinel,"unchanged");
      fs.mkdirSync(home,{{recursive:true}});
      const label = {json.dumps(unsafe)};
      const target = label==="home"?home:label==="MEMORY.md"?path.join(home,"memory",label):path.join(home,label);
      if(label==="home")fs.rmdirSync(home);
      fs.mkdirSync(path.dirname(target),{{recursive:true}});
      fs.symlinkSync(["MEMORY.md","state.json"].includes(label)?sentinel:outside,target);
      let error="";try{{sa.ensureAgentWorkspace({{agentName:"reviewer",cwd}});}}catch(e){{error=e.message;}}
      console.log(JSON.stringify({{refused:!!error,error,sentinel:fs.readFileSync(sentinel,"utf8"),outside:fs.readdirSync(outside)}}));
    ''', tmp_path)
    assert result["refused"] is True
    assert "symlink" in result["error"].lower()
    assert result["sentinel"] == "unchanged" and result["outside"] == ["sentinel"]


@pytest.mark.parametrize("git_kind", ["file", "directory"])
def test_provision_never_disguises_a_git_workspace(tmp_path: Path, git_kind: str) -> None:
    result = run(f'''
      const workspace = sa.agentWorkspacePath("reviewer");fs.mkdirSync(workspace,{{recursive:true}});
      const git = path.join(workspace,".git");
      if({json.dumps(git_kind)}==="file")fs.writeFileSync(git,"gitdir: /legacy");else fs.mkdirSync(git);
      fs.writeFileSync(path.join(workspace,"output"),"only copy");
      let error="";try{{sa.ensureAgentWorkspace({{agentName:"reviewer",cwd}});}}catch(e){{error=e.message;}}
      console.log(JSON.stringify({{error,kept:fs.existsSync(git),output:fs.readFileSync(path.join(workspace,"output"),"utf8")}}));
    ''', tmp_path)
    assert result["error"] and result["kept"] is True and result["output"] == "only copy"


def test_provision_preserves_extra_state_and_respects_a_memory_writer_lock(tmp_path: Path) -> None:
    result = run('''
      sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const home=sa.agentHomePath("reviewer");const file=path.join(home,"state.json");
      const state=JSON.parse(fs.readFileSync(file,"utf8"));state.retainedMetadata={label:"Do not discard"};
      fs.writeFileSync(file,JSON.stringify(state));
      sa.ensureAgentWorkspace({agentName:"reviewer",cwd});
      const metadataKept=JSON.parse(fs.readFileSync(file,"utf8")).retainedMetadata;
      const before=fs.readFileSync(file);const lock=file+".lock";fs.writeFileSync(lock,"other-process");
      let refused=false;try{sa.ensureAgentWorkspace({agentName:"reviewer",cwd:path.join(cwd,"another")});}catch{refused=true;}
      console.log(JSON.stringify({metadataKept,refused,unchanged:fs.readFileSync(file).equals(before),lock:fs.readFileSync(lock,"utf8")}));
    ''', tmp_path)
    assert result == {"metadataKept":{"label":"Do not discard"},"refused":True,"unchanged":True,"lock":"other-process"}


def test_malformed_state_is_not_overwritten(tmp_path: Path) -> None:
    result = run('''
      const home=sa.agentHomePath("reviewer");fs.mkdirSync(home,{recursive:true});
      const file=path.join(home,"state.json");fs.writeFileSync(file,"{invalid");
      let refused=false;try{sa.ensureAgentWorkspace({agentName:"reviewer",cwd});}catch{refused=true;}
      console.log(JSON.stringify({refused,content:fs.readFileSync(file,"utf8")}));
    ''', tmp_path)
    assert result == {"refused": True, "content": "{invalid"}


def test_parallel_provisioners_publish_complete_state_and_share_creation_time(tmp_path: Path) -> None:
    result = run(f'''
      const {{spawn}}=await import("node:child_process");
      const script=`import * as sa from {json.dumps(WORKSPACE)};import fs from "node:fs";
        sa.ensureAgentWorkspace({{agentName:"reviewer",cwd:process.env.PI_TEST_CWD}});
        console.log(fs.readFileSync(sa.agentHomePath("reviewer")+"/state.json","utf8"));`;
      const states=await Promise.all(Array.from({{length:6}},()=>new Promise((resolve,reject)=>{{
        const child=spawn(process.execPath,["--input-type=module","--eval",script],{{env:process.env}});
        let out="",err="";child.stdout.on("data",d=>out+=d);child.stderr.on("data",d=>err+=d);
        child.on("error",reject);child.on("close",code=>code?reject(new Error(err)):resolve(JSON.parse(out)));
      }})));
      const home=sa.agentHomePath("reviewer");
      console.log(JSON.stringify({{states,temp:fs.readdirSync(home).filter(n=>n.endsWith(".tmp")),
        final:JSON.parse(fs.readFileSync(path.join(home,"state.json"),"utf8"))}}));
    ''', tmp_path)
    assert len({state["createdAt"] for state in result["states"]}) == 1
    assert result["final"]["createdAt"] == result["states"][0]["createdAt"]
    assert result["temp"] == []


def test_git_preserve_and_release_apis_are_removed(tmp_path: Path) -> None:
    result = run('console.log(JSON.stringify({keys:Object.keys(sa)}));', tmp_path)
    assert "preserveAgentWorkspace" not in result["keys"]
    assert "releaseAgentWorkspace" not in result["keys"]
    assert "workspacesRoot" not in result["keys"]
    source = (PACKAGE / "src" / "workspace.ts").read_text(encoding="utf-8")
    assert "node:child_process" not in source


# --- Merged from test_spawn_extensions.py ---
"""Agent extensions and capability tools are contributed by the caller.

Contract: packages/subagents/features/spawn-extension-contribution.feature

The spawner used to hardcode both: an extension constant pointing at its
own package's index.ts, and a capability set naming `agent_event` and `work` —
tools registered by a different package. That is what would have made the
subagents / task / agent-teams split impossible: the execution layer would have
loaded another package's Agent extension and granted two tools it does not
register.

These tests use deliberately neutral capability names (`alpha_tool`, `beta_tool`)
rather than the real coordination pair, because the property under test is that
the spawner is agnostic. The agent-teams suite asserts what that package actually
contributes.

The command line is read from inside a spawned child that dumps its own
`process.argv`, so these prove what the child was launched with rather than what
a builder function returned.
"""


import json

from subagents_helpers import PACKAGE, run_node, source

SPAWNER = (PACKAGE / "src" / "spawner.ts").as_uri()

FIRST_EXTENSION = "/tmp/first-agent.ts"
SECOND_EXTENSION = "/tmp/second-agent.ts"
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
            agentName: "argv-probe",
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


# ── Rule: each contributing package supplies its own Agent extension ──


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
    assert "--extension" not in argv, "a spawn contributing nothing must load no Agent extension"
    assert "--no-extensions" in argv
    assert flags_of(argv, "--tools") == ["read,bash"], (
        "with no contributed capability set the allowlist is exactly the role's grant"
    )


# ── Rule: a declared capability must have something to register it ──


def test_capability_tools_without_an_extension_are_refused() -> None:
    payload = spawn_with_argv_probe(f"capabilityTools: {CAPABILITY_TOOLS},")
    error = str(payload.get("spawnError", ""))
    assert "alpha_tool" in error and "no Agent extension" in error, error
    # A refused spawn must not start a child at all.
    assert "stderr" not in payload, "no child process may be started for a refused spawn"
    assert "exitCode" not in payload


def test_the_spawner_hardcodes_no_extension_path_or_capability_tool_names() -> None:
    """The coupling that would have blocked the split must not come back."""
    spawner = source("spawner.ts")
    assert "AGENT_EXTENSION" not in spawner, "the spawner must not resolve its own package's Agent entry"
    assert "import.meta.url" not in spawner, "the spawner must not derive an extension path from itself"
    assert "agent_event" not in spawner, "the spawner must not name another package's tool"
    assert '"work"' not in spawner, "the spawner must not name another package's tool"
    assert "capabilityTools" in spawner, "the contributed set must be a parameter, not a constant"


# ── Rule: a contributed set widens the grant and the universe ──


def test_a_contributed_capability_set_widens_the_grant_and_the_universe() -> None:
    payload = run_node(
        f'''\
        import {{ resolveAgentTools, unknownAgentTools, agentToolUniverse }} from "{SPAWNER}";
        const contributed = ["alpha_tool", "beta_tool"];
        console.log(JSON.stringify({{
          withCapability: resolveAgentTools(["read", "alpha_tool"], contributed),
          bare: resolveAgentTools(["read"], []),
          emptyRole: resolveAgentTools([], contributed),
          undefinedRole: resolveAgentTools(undefined, contributed),
          unknownWithCapability: unknownAgentTools(["read", "mcp__x"], contributed),
          unknownBare: unknownAgentTools(["alpha_tool", "read"], []),
          universeHasCapability: agentToolUniverse(contributed).includes("alpha_tool"),
          universeBare: agentToolUniverse([]).includes("alpha_tool"),
          universeHasBuiltins: agentToolUniverse([]).includes("read"),
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


# --- Merged from test_native_fixture_isolation.py ---
"""Native evidence must come from the pinned cohort and an isolated parent."""

import secrets
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from subagents_helpers import REPO
from native_support import native_command


def test_native_parent_does_not_inherit_credentials_or_startup_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambient = ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "NODE_OPTIONS", "HTTPS_PROXY", "XDG_CONFIG_HOME")
    for name in ambient:
        monkeypatch.setenv(name, secrets.token_hex(16))
    fixture = native_command.__wrapped__(tmp_path, SimpleNamespace())
    try:
        _, env, _, _, _ = next(fixture)
        inherited_names = sorted(set(ambient) & set(env))
        assert inherited_names == []
        assert env["HOME"] == str(tmp_path)
        assert env["PI_CODING_AGENT_DIR"] == str(tmp_path / "agent")
    finally:
        fixture.close()


def test_native_parent_uses_repository_pi_when_global_pi_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/fixture-global-pi")
    fixture = native_command.__wrapped__(tmp_path, SimpleNamespace())
    try:
        command, _, _, _, _ = next(fixture)
        assert command[0] == str(REPO / "node_modules" / ".bin" / "pi")
    finally:
        fixture.close()
