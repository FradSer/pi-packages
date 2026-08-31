from __future__ import annotations

import json
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]


def run_bun(source: str) -> dict[str, object]:
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def defaults_layer() -> str:
    return json.dumps(
        {
            "source": "built-in defaults",
            "policies": "${DEFAULTS}",
        }
    )


def evaluate(layers_json: str, tool_name: str, args: dict) -> dict[str, object]:
    src = f"""
        import {{ DEFAULT_POLICIES, evaluate, mergeLayers }} from './packages/pi-continual-learning/extensions/guardrail-engine.ts';
        const layers = {layers_json}.map((l) =>
          l.source === "built-in defaults" ? {{ ...l, policies: DEFAULT_POLICIES }} : l,
        );
        const config = mergeLayers(layers);
        const decision = evaluate(config, {{ toolName: {json.dumps(tool_name)}, args: {json.dumps(args)} }});
        console.log(JSON.stringify(decision ? {{ matched: true, ...decision }} : {{ matched: false }}));
    """
    return run_bun(src)


def merge_only(layers_json: str) -> dict[str, object]:
    src = f"""
        import {{ DEFAULT_POLICIES, mergeLayers }} from './packages/pi-continual-learning/extensions/guardrail-engine.ts';
        const layers = {layers_json}.map((l) =>
          l.source === "built-in defaults" ? {{ ...l, policies: DEFAULT_POLICIES }} : l,
        );
        const config = mergeLayers(layers);
        console.log(JSON.stringify({{ names: config.policies.map((p) => p.name), errors: config.errors }}));
    """
    return run_bun(src)


def test_default_policy_blocks_interactive_auth_with_guidance() -> None:
    layers = json.dumps([{"source": "built-in defaults"}])
    decision = evaluate(
        layers,
        "bash",
        {"command": "npm login --registry=https://registry.npmjs.org/"},
    )
    assert decision["matched"] is True
    assert decision["policyName"] == "no-interactive-auth-automation"
    assert "their own terminal" in str(decision["reason"])


def test_non_matching_call_passes_through() -> None:
    layers = json.dumps([{"source": "built-in defaults"}])
    decision = evaluate(layers, "bash", {"command": "pnpm test"})
    assert decision["matched"] is False


def test_require_gate_scopes_ui_width_policy() -> None:
    ui_policy = {
        "name": "ui-fixed-width",
        "tools": ["edit", "write"],
        "require": {"path": "path", "pattern": "\\.(tsx|css)$"},
        "patterns": ["width:\\s*\\d{3,}px"],
        "action": "block",
        "reason": "Use design tokens or responsive units.",
    }
    layers = json.dumps([{"source": "project", "policies": [ui_policy]}])

    blocked = evaluate(
        layers,
        "edit",
        {"path": "src/Button.tsx", "edits": [{"newText": "width: 480px"}]},
    )
    assert blocked["matched"] is True
    assert blocked["policyName"] == "ui-fixed-width"
    assert "responsive" in str(blocked["reason"])

    passed = evaluate(
        layers,
        "edit",
        {"path": "docs/notes.md", "edits": [{"newText": "width: 480px"}]},
    )
    assert passed["matched"] is False


def test_innermost_policy_definition_wins() -> None:
    outer = {
        "name": "shared-rule",
        "pattern": "alpha",
        "action": "block",
        "reason": "outer reason",
    }
    inner = {
        "name": "shared-rule",
        "pattern": "beta",
        "action": "block",
        "reason": "inner reason",
    }
    layers = json.dumps(
        [
            {"source": "user", "policies": [outer]},
            {"source": "project", "policies": [inner]},
        ]
    )
    hit_outer = evaluate(layers, "bash", {"command": "echo alpha"})
    assert hit_outer["matched"] is False
    hit_inner = evaluate(layers, "bash", {"command": "echo beta"})
    assert hit_inner["matched"] is True
    assert "inner reason" in str(hit_inner["reason"])


def test_harness_target_resolution_defaults_to_project_local_and_supports_flags() -> None:
    source = """
        import { resolveHarnessTarget } from './packages/pi-continual-learning/extensions/guardrails.ts';
        const cwd = '/tmp/my-project';
        const agentDir = '/tmp/user/agent';
        console.log(JSON.stringify({
          defaultTarget: resolveHarnessTarget('Block edits that add hard-coded colors', cwd, agentDir),
          globalFlag: resolveHarnessTarget('--global Block edits', cwd, agentDir),
          globalShort: resolveHarnessTarget('-g Block edits', cwd, agentDir),
          sharedFlag: resolveHarnessTarget('--shared Block edits', cwd, agentDir),
          projectFlag: resolveHarnessTarget('--project Block edits', cwd, agentDir),
          repoFlag: resolveHarnessTarget('--repo Block edits', cwd, agentDir),
          projectLocalFlag: resolveHarnessTarget('--local Block edits', cwd, agentDir),
          globalSharedFlag: resolveHarnessTarget('--global-shared Block edits', cwd, agentDir),
        }));
    """
    result = run_bun(source)
    assert result["defaultTarget"]["scope"] == "project.local"
    assert result["defaultTarget"]["targetFile"] == "/tmp/my-project/.pi/harness.local.json"
    assert result["defaultTarget"]["request"] == "Block edits that add hard-coded colors"

    assert result["globalFlag"]["scope"] == "user.local"
    assert result["globalFlag"]["targetFile"] == "/tmp/user/agent/harness.local.json"
    assert result["globalFlag"]["request"] == "Block edits"

    assert result["globalShort"]["scope"] == "user.local"
    assert result["globalShort"]["targetFile"] == "/tmp/user/agent/harness.local.json"

    assert result["sharedFlag"]["scope"] == "project"
    assert result["sharedFlag"]["targetFile"] == "/tmp/my-project/.pi/harness.json"
    assert result["sharedFlag"]["request"] == "Block edits"

    assert result["projectFlag"]["scope"] == "project"
    assert result["repoFlag"]["scope"] == "project"

    assert result["projectLocalFlag"]["scope"] == "project.local"
    assert result["projectLocalFlag"]["targetFile"] == "/tmp/my-project/.pi/harness.local.json"

    assert result["globalSharedFlag"]["scope"] == "user"
    assert result["globalSharedFlag"]["targetFile"] == "/tmp/user/agent/harness.json"


def test_harness_prompt_routes_a_direct_rule_request() -> None:
    source = """
        import { buildHarnessRulePrompt } from './packages/pi-continual-learning/extensions/guardrails.ts';
        console.log(JSON.stringify(buildHarnessRulePrompt('Block edits that add hard-coded colors', '/tmp/project/.pi/harness.local.json', 'project personal harness.local.json')));
    """
    result = run_bun(source)
    prompt = result
    assert 'Block edits that add hard-coded colors' in str(prompt)
    assert '/tmp/project/.pi/harness.local.json' in str(prompt)
    assert 'project personal harness.local.json' in str(prompt)
    assert 'Preserve every existing policy' in str(prompt)
    assert 'Do not use find, fffind, grep, rg, read-directory, or any other discovery step' in str(prompt)
    assert 'Execute this exact sequence' in str(prompt)
    assert 'returns ENOENT' in str(prompt)
    assert 'Do not merely explain' in str(prompt)
    assert 'Do not write scope or rule' in str(prompt)
    assert 'tool-call gates only' in str(prompt)


def test_global_harness_target_initializes_exact_path_and_preserves_existing(tmp_path: Path) -> None:
    missing = tmp_path / 'agent' / 'harness.local.json'
    existing = tmp_path / 'existing' / 'harness.local.json'
    existing.parent.mkdir()
    original = {
        'policies': [{'name': 'keep', 'pattern': 'keep', 'action': 'block', 'reason': 'keep'}],
        'disabled': ['disabled-rule'],
        'skillPrompts': {'review': {'prompt': 'keep this', 'target': 'system'}},
        'custom': {'preserve': True},
    }
    existing.write_text(json.dumps(original), encoding='utf-8')
    source = f"""
        import fs from 'node:fs/promises';
        import {{ ensureGlobalHarnessTarget }} from './packages/pi-continual-learning/extensions/guardrails.ts';
        const missing = await ensureGlobalHarnessTarget({json.dumps(str(missing))});
        const before = await fs.readFile({json.dumps(str(existing))}, 'utf8');
        const reused = await ensureGlobalHarnessTarget({json.dumps(str(existing))});
        const after = await fs.readFile({json.dumps(str(existing))}, 'utf8');
        console.log(JSON.stringify({{
          created: missing.created,
          missingPath: missing.path,
          initialized: JSON.parse(await fs.readFile({json.dumps(str(missing))}, 'utf8')),
          reused: reused.created,
          preservedBytes: before === after,
          preserved: JSON.parse(after),
        }}));
    """
    result = run_bun(source)
    assert result['created'] is True
    assert result['missingPath'] == str(missing)
    assert result['initialized'] == {'policies': [], 'disabled': [], 'skillPrompts': {}}
    assert result['reused'] is False
    assert result['preservedBytes'] is True
    assert result['preserved'] == original


def test_global_harness_target_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / 'harness.local.json'
    outside = tmp_path / 'outside.json'
    outside.write_text('{}', encoding='utf-8')
    target.symlink_to(outside)
    source = f"""
        import {{ ensureGlobalHarnessTarget }} from './packages/pi-continual-learning/extensions/guardrails.ts';
        try {{ await ensureGlobalHarnessTarget({json.dumps(str(target))}); console.log(JSON.stringify({{ rejected: false }})); }}
        catch (error) {{ console.log(JSON.stringify({{ rejected: /regular file/.test(String(error)) }})); }}
    """
    result = run_bun(source)
    assert result['rejected'] is True


def test_invalid_skill_prompt_user_message_pattern_is_skipped_without_hiding_valid_siblings() -> None:
    layers = json.dumps(
        [
            {
                "source": "project",
                "skillPrompts": {
                    "broken": {"prompt": "bad", "target": "system", "userMessagePattern": "(["},
                    "valid": {"prompt": "good", "target": "system", "userMessagePattern": "^live$"},
                },
            }
        ]
    )
    source = f"""
        import {{ mergeLayers }} from './packages/pi-continual-learning/extensions/guardrail-engine.ts';
        const result = mergeLayers({layers});
        console.log(JSON.stringify({{ skillPrompts: result.skillPrompts, errors: result.errors }}));
    """
    result = run_bun(source)
    assert "broken" not in result["skillPrompts"]
    assert result["skillPrompts"]["valid"]["userMessagePattern"] == "^live$"
    assert any("broken" in error and "invalid regex" in error for error in result["errors"])


def test_legacy_scope_and_rule_fields_are_rejected_with_schema_guidance() -> None:
    legacy = {
        "name": "impeccable-live-runtime-stability",
        "action": "confirm",
        "scope": {"commands": ["node live.mjs"]},
        "rule": "verify the live server before restarting",
    }
    valid = {
        "name": "valid-live-runtime-stability",
        "tools": ["bash"],
        "paths": ["command"],
        "pattern": r"node\\s+.*live\\.mjs",
        "action": "confirm",
        "reason": "Verify the live server before restarting.",
    }
    merged = merge_only(json.dumps([{"source": "project", "policies": [legacy, valid]}]))
    assert "impeccable-live-runtime-stability" not in merged["names"]
    assert "valid-live-runtime-stability" in merged["names"]
    diagnostics = " ".join(str(error) for error in merged["errors"])
    assert "unsupported field(s): scope, rule" in diagnostics
    assert "tools, paths, pattern, patterns" in diagnostics
    assert "reason" in diagnostics


def test_policy_declaration_requires_one_supported_pattern_form() -> None:
    source = """
        import { validatePolicyDeclaration } from './packages/pi-continual-learning/extensions/guardrail-engine.ts';
        const results = {
          missing: validatePolicyDeclaration({ name: 'missing' }),
          both: validatePolicyDeclaration({ name: 'both', pattern: 'a', patterns: ['b'] }),
          empty: validatePolicyDeclaration({ name: 'empty', patterns: [] }),
          valid: validatePolicyDeclaration({ name: 'valid', tools: ['bash'], paths: ['command'], pattern: 'live', action: 'confirm', reason: 'check first' }),
        };
        console.log(JSON.stringify(results));
    """
    result = run_bun(source)
    assert any("requires a non-empty pattern" in str(error) for error in result["missing"])
    assert any("not both" in str(error) for error in result["both"])
    assert any("non-empty array" in str(error) for error in result["empty"])
    assert result["valid"] == []


def test_disabled_names_and_invalid_regex_are_tolerated() -> None:
    layers = json.dumps(
        [
            {
                "source": "user",
                "policies": [
                    {"name": "broken", "pattern": "([unclosed", "action": "block", "reason": "x"},
                    {"name": "bad-paths", "paths": [42], "pattern": "x", "action": "block", "reason": "x"},
                    {"name": "ok", "pattern": "deploy-prod", "action": "block", "reason": "ask first"},
                ],
                "disabled": ["no-otp-in-chat"],
            }
        ]
    )
    merged = merge_only(layers)
    assert "no-otp-in-chat" not in merged["names"]
    assert "bad-paths" not in merged["names"]
    assert "ok" in merged["names"]
    assert any("invalid regex" in str(e) for e in merged["errors"])
    assert any("paths must be an array of strings" in str(e) for e in merged["errors"])
