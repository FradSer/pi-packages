"""Shared AGENTS.md consolidation fixtures.

`applyPlanScript`, `extractionOps`, `prepareExtractionRoots` and the frozen
snapshot are used by both the AGENTS.md plan tests and the harness follow-up
tests, so they live here instead of being imported across test modules.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from support import PKG_DIR

MODULE = "./packages/continual-learning/extensions/agents-md-consolidation.ts"

SNAPSHOT_OBJECT = {
    "entries": [
        {"message": {"role": "user", "content": [{"type": "text", "text": "the build failed because\nstale fixtures broke the build again"}]}},
        {"type": "tool_execution_end", "result": "npm test failed with ERR_PNPM_NO_SCRIPT"},
        {"message": {"role": "assistant", "content": "assistant invented evidence"}},
        {"type": "tool_execution_end", "toolName": "write", "policyName": "metadata-only", "result": "ordinary result"},
        {"message": {"role": "toolResult", "content": [{"type": "text", "text": "SDK tool result evidence"}]}},
        {"message": {"role": "user", "content": "stale fixtures broke the build again"}},
    ]
}
SNAPSHOT = json.dumps(SNAPSHOT_OBJECT)


def evidence(quote: str, entry_index: int = 0, occurrences: int = 1, kind: str = "gap") -> dict:
    return {"kind": kind, "quote": quote, "entryIndex": entry_index, "occurrences": occurrences}


def apply_plan_script(
    project: Path,
    agent: Path,
    run_dir: Path,
    operations: list[dict],
    *,
    cancelled_after: int | None = None,
    fail_at: str | None = None,
) -> str:
    run = {
        "manifest": {
            "runId": "run_test",
            "scopeDigest": "scope",
            "snapshotDigest": "snapshot",
            "runDir": str(run_dir),
            "harnessDir": str(agent / "memory" / "project"),
            "publicDir": str(project / ".memory"),
        }
    }
    doc = (project / "AGENTS.md").read_text(encoding="utf-8")
    planning = {
        "run": run,
        "targetPath": str(project / "AGENTS.md"),
        "docBytesBase64": base64.b64encode(doc.encode()).decode(),
        "doc": doc,
        "preBytes": len(doc.encode()),
        "snapshotText": SNAPSHOT,
        "rawPlan": {"kind": "agents-md-consolidation-plan", "operations": operations},
        "operations": operations,
        "droppedCount": 0,
        "durationMs": 1,
    }
    return f"""
      import {{ applyAgentsMdConsolidationPlan }} from '{MODULE}';
      const state = {{ active: true, generation: 1, cancelled: false }};
      const opts = {{ pkgDir: {json.dumps(str(PKG_DIR))}, cwd: {json.dumps(str(project))}, reason: 'test', budgetBytes: 16384, disabled: false, availableSkills: ['using-open-artifacts'], transactionFault: {json.dumps(fail_at)} }};
      let checks = 0;
      const planning = {json.dumps(planning)};
      planning.docBytes = Buffer.from(planning.docBytesBase64, 'base64');
      delete planning.docBytesBase64;
      const result = await applyAgentsMdConsolidationPlan({{ ui: {{ notify() {{}} }} }}, state, opts, planning, 1, {json.dumps(cancelled_after)} === null ? undefined : () => ++checks < {json.dumps(cancelled_after)});
      const read = async (file) => await Bun.file(file).text().catch(() => null);
      const exists = async (file) => await Bun.file(file).exists();
      console.log(JSON.stringify({{
        result,
        agents: await read({json.dumps(str(project / 'AGENTS.md'))}),
        harnessMemory: await read({json.dumps(str(agent / 'memory' / 'project' / 'fixture-regeneration.md'))}),
        publicMemory: await read({json.dumps(str(project / '.memory' / 'fixture-regeneration.md'))}),
        harnessIndex: await read({json.dumps(str(agent / 'memory' / 'project' / 'MEMORY.md'))}),
        publicIndex: await read({json.dumps(str(project / '.memory' / 'MEMORY.md'))}),
        harnessConfig: await read({json.dumps(str(project / '.pi' / 'harness.json'))}),
        preReceipt: JSON.parse((await read({json.dumps(str(run_dir / 'agents-pre-receipt.json'))})) ?? 'null'),
        preReceiptExists: await exists({json.dumps(str(run_dir / 'agents-pre-receipt.json'))}),
        receiptExists: await exists({json.dumps(str(run_dir / 'agents-post-receipt.json'))}),
      }}));
    """


def extraction_ops(memory_type: str = "project", classification: str = "safe") -> list[dict]:
    return [
        {
            "op": "extractUnit",
            "oldText": "- Regenerate fixtures after schema changes",
            "extraction": {
                "target": "memory",
                "memoryName": "fixture-regeneration.md",
                "description": "Regenerate fixtures after schema changes",
                "type": memory_type,
                "classification": classification,
            },
            "evidence": [evidence("stale fixtures broke the build again", 0)],
        },
        {
            "op": "extractUnit",
            "oldText": "- Use coda0.com as the default artifacts host",
            "extraction": {
                "target": "skillRule",
                "ruleId": "artifact-host",
                "skillName": "using-open-artifacts",
                "instructions": "Use coda0.com as the default instance.",
            },
            "evidence": [evidence("npm test failed with ERR_PNPM_NO_SCRIPT", 1)],
        },
    ]


def prepare_extraction_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    agent = tmp_path / "agent"
    run_dir = tmp_path / "run"
    (project / ".memory").mkdir(parents=True)
    (project / ".pi").mkdir()
    (agent / "memory" / "project").mkdir(parents=True)
    run_dir.mkdir()
    (project / "AGENTS.md").write_text(
        "# Rules\n\n- Regenerate fixtures after schema changes\n- Use coda0.com as the default artifacts host\n",
        encoding="utf-8",
    )
    harness_index = "# Memory Index\n\n- [existing-private.md](existing-private.md) (harness only)\n"
    public_index = "# Memory Index\n"
    (agent / "memory" / "project" / "existing-private.md").write_text("private\n", encoding="utf-8")
    (agent / "memory" / "project" / "MEMORY.md").write_text(harness_index, encoding="utf-8")
    (project / ".memory" / "MEMORY.md").write_text(public_index, encoding="utf-8")
    return project, agent, run_dir