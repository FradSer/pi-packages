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


def test_disabled_names_and_invalid_regex_are_tolerated() -> None:
    layers = json.dumps(
        [
            {
                "source": "user",
                "policies": [
                    {"name": "broken", "pattern": "([unclosed", "action": "block", "reason": "x"},
                    {"name": "ok", "pattern": "deploy-prod", "action": "block", "reason": "ask first"},
                ],
                "disabled": ["no-otp-in-chat"],
            }
        ]
    )
    merged = merge_only(layers)
    assert "no-otp-in-chat" not in merged["names"]
    assert "ok" in merged["names"]
    assert any("invalid regex" in str(e) for e in merged["errors"])
