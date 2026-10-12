"""Zero-paid contracts for deterministic official acceptance and developer guidance."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[1]


def test_deterministic_monitor_acceptance_has_no_model_entry_point(tmp_path: Path) -> None:
    """Given exact compiler outcomes, normal acceptance admits no model workflow."""
    manifest = json.loads((REPO / "package.json").read_text())
    for name in ["test:e2e:ai", "test:e2e:ai:offline", "test:e2e:paid"]:
        assert name not in manifest["scripts"], name
    for name in ["ai", "@ai-sdk/openai-compatible", "zod"]:
        assert name not in manifest["devDependencies"], name
    for name in ["e2e.monitor-ai.config.ts", "e2e.paid.config.ts", "tests/official-e2e-ai/monitor.e2e.ts", "tests/official-e2e-support/monitor-ai.ts", "tests/official-e2e-paid/monitor-review.e2e.ts"]:
        assert not (REPO / name).exists(), name
    config = json.loads((REPO / "tsconfig.e2e.json").read_text())
    assert config["include"] == ["e2e.config.ts", "tests/official-e2e/**/*.e2e.ts"]
    result = subprocess.run(["node", "--import", "tsx", "--input-type=module", "-e", "import assert from 'node:assert/strict'; import config from './e2e.config.ts'; assert.deepEqual(config.agents, {}); assert.deepEqual(config.tests, ['tests/official-e2e/**/*.e2e.ts']);"], cwd=REPO, env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)}, text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_developer_docs_have_one_complete_integration_section() -> None:
    scenarios = re.findall(r"^  Scenario: (.+)$", (REPO / "features/tester-army-e2e.feature").read_text(), re.M)
    assert len(scenarios) == 8
    for filename, headings in [("README.md", ["## Development", "## Adding a package", "## Publishing", "## License"]), ("README.zh-CN.md", ["## 开发", "## 添加包", "## 发布", "## 许可证"])]:
        text = (REPO / filename).read_text()
        for heading in headings:
            assert text.splitlines().count(heading) == 1, (filename, heading)
        for scenario in scenarios:
            assert text.count("| " + scenario + " |") == 1, (filename, scenario)
        assert "test:e2e:ai" not in text
        assert "test:e2e:paid" not in text
        assert "docs/history/monitor-e2e-ai.md" in text
        assert "agent.act" in text and "agent.assert" in text


def test_monitor_exact_assertions_and_real_pi_paths_are_preserved() -> None:
    text = (REPO / "tests/official-e2e/monitor-workflows.e2e.ts").read_text()
    for marker in ["transport-matrix-fixture.ts", "toolCallId", "completion", "TS2322", "invalid-verification.ts", "invalid_json_result", "result_missing", "timeout", "toBe(7)", "toBeGreaterThan(0)"]:
        assert marker in text, marker
    for path in (REPO / "tests/official-e2e").glob("*.e2e.ts"):
        assert not re.search(r"agent\.(act|assert|waitFor|extract)\s*\(", path.read_text()), path
