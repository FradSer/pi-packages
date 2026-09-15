from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[3]


def run_bun(source: str, env: dict[str, str] | None = None) -> dict:
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        text=True,
        capture_output=True,
        env={**os.environ, **(env or {})},
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_current_task_slice_keeps_completed_task_evidence_only() -> None:
    result = run_bun(r"""
      import { currentTaskSlice } from './packages/continual-learning/extensions/incremental-learning.ts';
      const message = (role, text) => ({ type: 'message', message: { role, content: [{ type: 'text', text }] } });
      const entries = [
        message('user', 'old task'),
        message('assistant', 'old result'),
        { type: 'compaction', summary: 'older compacted history' },
        message('user', 'current task'),
        message('assistant', 'I will retry the edit.'),
        message('toolResult', 'current tool result'),
        { type: 'custom', customType: 'extension-repair', content: 'current extension repair' },
        message('assistant', 'current final result'),
        message('user', 'queued next task'),
      ];
      console.log(JSON.stringify(currentTaskSlice(entries)));
    """)
    serialized = json.dumps(result)
    assert result["kind"] == "learning-task-slice"
    assert "current task" in serialized
    assert "current tool result" in serialized
    assert "current extension repair" in serialized
    assert "current final result" in serialized
    assert "old task" not in serialized
    assert "older compacted history" not in serialized
    assert "queued next task" not in serialized


def test_large_task_slice_preserves_the_final_result() -> None:
    result = run_bun(r"""
      import { currentTaskSlice } from './packages/continual-learning/extensions/incremental-learning.ts';
      const entries = [{ message: { role: 'user', content: 'large task' } }];
      for (let index = 0; index < 120; index += 1) entries.push({ message: { role: 'toolResult', content: 'x'.repeat(6000) } });
      entries.push({ message: { role: 'assistant', content: 'FINAL_RESULT' } });
      const slice = currentTaskSlice(entries);
      console.log(JSON.stringify({ kind: slice.kind, count: slice.entries.length, first: slice.entries[0], last: slice.entries.at(-1) }));
    """)
    serialized = json.dumps(result)
    assert "large task" in serialized
    assert "FINAL_RESULT" in serialized
    assert result["count"] <= 96


def test_selector_uses_metadata_only_accepts_all_related_and_writes_each_body_once() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-selector-") as temporary:
        result = run_bun(r"""
          import { mock } from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import { execFileSync } from 'node:child_process';
          const cwd = path.join(process.env.TEST_ROOT, 'project');
          const outputDir = path.join(process.env.TEST_ROOT, 'output');
          fs.mkdirSync(cwd, { recursive: true });
          execFileSync('git', ['init', '-q', cwd]);
          fs.mkdirSync(path.join(cwd, '.memory'), { recursive: true });
          const selected = [];
          for (let index = 0; index < 10; index += 1) {
            const name = `related-${index}.md`;
            selected.push(name);
            fs.writeFileSync(path.join(cwd, '.memory', name), `---\nname: related-${index}\ndescription: Related selector fact ${index}\ntype: feedback\n---\nUNIQUE_BODY_${index}\n`);
          }
          fs.writeFileSync(path.join(cwd, '.memory', 'unrelated.md'), '---\nname: unrelated\ndescription: Unrelated fact\ntype: project\n---\nUNSELECTED_BODY\n');
          let workerInput;
          const kit = await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts', () => ({
            ...kit,
            runPiWorker: async input => {
              workerInput = input;
              const digest = /Context digest:\s*([^\n]+)/.exec(input.prompt)[1];
              return {
                text: `Selection follows.\n\`\`\`json\n${JSON.stringify({
                  kind: 'incremental-memory-selection', version: 1, contextDigest: digest,
                  selected, memory: true, harness: false, agents: false, reason: 'All ten metadata entries are directly related.',
                })}\n\`\`\`\nDone.`,
                exitCode: 0, stderr: '', cancelled: false,
              };
            },
          }));
          const { selectIncrementalLearning } = await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const outcome = await selectIncrementalLearning({
            cwd,
            taskSlice: { kind: 'learning-task-slice', version: 1, entries: [{ marker: 'TASK_SLICE_ONCE' }] },
            contextDigest: 'selector-digest',
            outputDir,
            registeredSkills: ['using-open-artifacts'],
          });
          const dossierText = fs.readFileSync(outcome.dossierPath, 'utf8');
          console.log(JSON.stringify({
            outcome: outcome.outcome,
            selected: outcome.selection?.selected,
            tools: workerInput.tools,
            minimal: workerInput.minimal,
            prompt: workerInput.prompt,
            taskOccurrences: dossierText.split('TASK_SLICE_ONCE').length - 1,
            bodyOccurrences: selected.map((_name, index) => dossierText.split(`UNIQUE_BODY_${index}`).length - 1),
            hasUnselectedBody: dossierText.includes('UNSELECTED_BODY'),
            registeredSkills: JSON.parse(dossierText).registeredSkills,
          }));
        """, {"TEST_ROOT": temporary})
    assert result["outcome"] == "selected"
    assert len(result["selected"]) == 10
    assert result["tools"] == []
    assert result["minimal"] is True
    assert "Related selector fact 0" in result["prompt"]
    assert "classification" in result["prompt"]
    assert '"type":"feedback"' in result["prompt"]
    assert '"classification":"safe"' in result["prompt"]
    assert "UNIQUE_BODY_0" not in result["prompt"]
    assert "/.memory/" not in result["prompt"]
    assert "minimum sufficient" in result["prompt"]
    assert "repository discovery" in result["prompt"]
    assert result["taskOccurrences"] == 1
    assert result["bodyOccurrences"] == [1] * 10
    assert result["hasUnselectedBody"] is False
    assert result["registeredSkills"] == ["using-open-artifacts"]


def test_empty_selection_keeps_memory_enabled_and_builds_empty_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-empty-selector-") as temporary:
        result = run_bun(r"""
          import { mock } from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import { execFileSync } from 'node:child_process';
          const cwd = path.join(process.env.TEST_ROOT, 'project');
          const outputDir = path.join(process.env.TEST_ROOT, 'output');
          fs.mkdirSync(cwd, { recursive: true });
          execFileSync('git', ['init', '-q', cwd]);
          fs.mkdirSync(path.join(cwd, '.memory'), { recursive: true });
          fs.writeFileSync(path.join(cwd, '.memory', 'existing.md'), '---\nname: existing\ndescription: Existing unrelated fact\ntype: project\n---\nEXISTING_BODY\n');
          const kit = await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts', () => ({
            ...kit,
            runPiWorker: async () => ({
              text: JSON.stringify({
                kind: 'incremental-memory-selection', version: 1, contextDigest: 'empty-digest',
                selected: [], memory: true, harness: false, agents: false,
                reason: 'New durable evidence has no related existing Memory.',
              }),
              exitCode: 0, stderr: '', cancelled: false,
            }),
          }));
          const { selectIncrementalLearning } = await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const outcome = await selectIncrementalLearning({
            cwd,
            taskSlice: { kind: 'learning-task-slice', version: 1, entries: [{ durable: 'new fact' }] },
            contextDigest: 'empty-digest',
            outputDir,
          });
          const dossier = JSON.parse(fs.readFileSync(outcome.dossierPath, 'utf8'));
          console.log(JSON.stringify({ outcome: outcome.outcome, selection: outcome.selection, selectedMemories: dossier.selectedMemories }));
        """, {"TEST_ROOT": temporary})
    assert result["outcome"] == "selected"
    assert result["selection"]["memory"] is True
    assert result["selection"]["selected"] == []
    assert result["selectedMemories"] == []


def test_selector_rejects_unknown_names_and_ambiguous_objects_without_dossier() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-invalid-selector-") as temporary:
        result = run_bun(r"""
          import { mock } from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import { execFileSync } from 'node:child_process';
          const cwd = path.join(process.env.TEST_ROOT, 'project');
          fs.mkdirSync(cwd, { recursive: true });
          execFileSync('git', ['init', '-q', cwd]);
          fs.mkdirSync(path.join(cwd, '.memory'), { recursive: true });
          fs.writeFileSync(path.join(cwd, '.memory', 'known.md'), '---\nname: known\ndescription: Known fact\ntype: project\n---\nKNOWN_BODY\n');
          let response = '';
          const kit = await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts', () => ({
            ...kit,
            runPiWorker: async () => ({ text: response, exitCode: 0, stderr: '', cancelled: false }),
          }));
          const { selectIncrementalLearning } = await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const selection = selected => ({
            kind: 'incremental-memory-selection', version: 1, contextDigest: 'invalid-digest', selected,
            memory: true, harness: false, agents: false, reason: 'test',
          });
          const unknownDir = path.join(process.env.TEST_ROOT, 'unknown');
          response = JSON.stringify(selection(['missing.md']));
          const unknown = await selectIncrementalLearning({
            cwd, taskSlice: { kind: 'learning-task-slice', version: 1, entries: [] },
            contextDigest: 'invalid-digest', outputDir: unknownDir,
          });
          const ambiguousDir = path.join(process.env.TEST_ROOT, 'ambiguous');
          response = `${JSON.stringify(selection(['known.md']))}\n${JSON.stringify(selection([]))}`;
          const ambiguous = await selectIncrementalLearning({
            cwd, taskSlice: { kind: 'learning-task-slice', version: 1, entries: [] },
            contextDigest: 'invalid-digest', outputDir: ambiguousDir,
          });
          console.log(JSON.stringify({
            unknown: unknown.outcome,
            ambiguous: ambiguous.outcome,
            unknownDossier: fs.existsSync(path.join(unknownDir, 'incremental-learning-dossier.json')),
            ambiguousDossier: fs.existsSync(path.join(ambiguousDir, 'incremental-learning-dossier.json')),
          }));
        """, {"TEST_ROOT": temporary})
    assert result == {
        "unknown": "failed",
        "ambiguous": "failed",
        "unknownDossier": False,
        "ambiguousDossier": False,
    }


def test_selector_timeout_is_cancelled_without_dossier_or_fallback() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-cancelled-selector-") as temporary:
        result = run_bun(r"""
          import { mock } from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import { execFileSync } from 'node:child_process';
          const cwd = path.join(process.env.TEST_ROOT, 'project');
          const outputDir = path.join(process.env.TEST_ROOT, 'output');
          fs.mkdirSync(cwd, { recursive: true });
          execFileSync('git', ['init', '-q', cwd]);
          fs.mkdirSync(path.join(cwd, '.memory'), { recursive: true });
          fs.writeFileSync(path.join(cwd, '.memory', 'known.md'), '---\nname: known\ndescription: Known fact\ntype: project\n---\nKNOWN_BODY\n');
          const kit = await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts', () => ({
            ...kit,
            runPiWorker: async () => ({ text: '', exitCode: 1, stderr: 'selector timed out', cancelled: true }),
          }));
          const { selectIncrementalLearning } = await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const outcome = await selectIncrementalLearning({
            cwd, taskSlice: { kind: 'learning-task-slice', version: 1, entries: [] },
            contextDigest: 'cancelled-digest', outputDir,
          });
          console.log(JSON.stringify({
            outcome: outcome.outcome,
            error: outcome.error,
            dossier: fs.existsSync(path.join(outputDir, 'incremental-learning-dossier.json')),
          }));
        """, {"TEST_ROOT": temporary})
    assert result["outcome"] == "cancelled"
    assert result["error"] == "selector timed out"
    assert result["dossier"] is False


def test_selector_rejects_unknown_fields_and_selected_body_drift() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-drift-selector-") as temporary:
        result = run_bun(r"""
          import { mock } from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import { execFileSync } from 'node:child_process';
          const cwd = path.join(process.env.TEST_ROOT, 'project');
          fs.mkdirSync(cwd, { recursive: true });
          execFileSync('git', ['init', '-q', cwd]);
          fs.mkdirSync(path.join(cwd, '.memory'), { recursive: true });
          const memoryFile = path.join(cwd, '.memory', 'known.md');
          fs.writeFileSync(memoryFile, '---\nname: known\ndescription: Known fact\ntype: project\n---\nORIGINAL_BODY\n');
          let mode = 'unknown-field';
          const kit = await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts', () => ({
            ...kit,
            runPiWorker: async () => {
              const selection = {
                kind: 'incremental-memory-selection', version: 1, contextDigest: 'drift-digest',
                selected: ['known.md'], memory: true, harness: false, agents: false, reason: 'test',
              };
              if (mode === 'drift') fs.writeFileSync(memoryFile, '---\nname: known\ndescription: Known fact\ntype: project\n---\nCHANGED_BODY_LONGER\n');
              return {
                text: JSON.stringify(mode === 'unknown-field' ? { ...selection, unexpected: true } : selection),
                exitCode: 0, stderr: '', cancelled: false,
              };
            },
          }));
          const { selectIncrementalLearning } = await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const run = outputDir => selectIncrementalLearning({
            cwd, taskSlice: { kind: 'learning-task-slice', version: 1, entries: [] },
            contextDigest: 'drift-digest', outputDir,
          });
          const unknownField = await run(path.join(process.env.TEST_ROOT, 'unknown-field'));
          mode = 'drift';
          fs.writeFileSync(memoryFile, '---\nname: known\ndescription: Known fact\ntype: project\n---\nORIGINAL_BODY\n');
          const drift = await run(path.join(process.env.TEST_ROOT, 'drift'));
          console.log(JSON.stringify({ unknownField: unknownField.outcome, drift: drift.outcome }));
        """, {"TEST_ROOT": temporary})
    assert result == {"unknownField": "failed", "drift": "failed"}
