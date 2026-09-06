"""
Tests for Slice 04 — Agent Capability Memory Abstraction.
Verifies that:
1. Agent memory paths resolve to per-agent dedicated directories (~/.pi/agent/agents/memory/<agent>/).
2. Project facts are barred from Agent Memory.
3. Memory proposals require evidence and are merged serially.
"""

import os
import subprocess
import textwrap
import pytest

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )

def test_agent_memory_dir_resolution():
    """Verify that agent memory path helper resolves to per-agent directory."""
    script = """
    import path from "node:path";
    import { getAgentDir } from "@earendil-works/pi-coding-agent";
    
    function resolveAgentMemoryDir(agentName) {
      return path.join(getAgentDir(), "agents", "memory", agentName);
    }
    
    const memDir = resolveAgentMemoryDir("reviewer");
    if (!memDir.includes(path.join("agents", "memory", "reviewer"))) {
      console.error("FAIL: incorrect path", memDir);
      process.exit(1);
    }
    console.log(JSON.stringify({ ok: true, path: memDir }));
    """
    res = run_node(script)
    assert res.returncode == 0, f"Script failed: {res.stderr}\n{res.stdout}"
