from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[3]


def run_bun(source: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        text=True,
        capture_output=True,
        env={**os.environ, **(env or {})},
        timeout=30,
        check=False,
    )


def test_expands_delta_to_validator_and_apply_compatible_full_plan() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-memory-plan-") as temporary:
        result = run_bun(
            r"""
              import { mkdir, readFile, writeFile } from 'node:fs/promises';
              import { join } from 'node:path';
              import {
                applyConsolidationPlan,
                sha256Digest,
              } from './packages/continual-learning/extensions/consolidation-run.ts';
              import { expandIncrementalMemoryPlan } from './packages/continual-learning/extensions/incremental-memory-plan.ts';

              const root = process.env.TEST_ROOT;
              const repo = join(root, 'repo');
              const harness = join(root, 'harness');
              const publicDir = join(root, 'public');
              const runDir = join(root, 'run');
              await mkdir(join(repo, 'src'), { recursive: true });
              await mkdir(harness, { recursive: true });
              await mkdir(publicDir, { recursive: true });
              await mkdir(runDir, { recursive: true });
              await writeFile(join(repo, 'src', 'config.ts'), 'export const mode = "strict";\n');
              await writeFile(join(harness, 'project_config.md'), 'old project fact\n');
              await writeFile(join(publicDir, 'project_config.md'), 'old project fact\n');
              await writeFile(join(harness, 'preference_style.md'), 'Prefer concise output.\n');
              await writeFile(join(harness, 'MEMORY.md'), '# Memory Index\n\n- [preference_style.md](preference_style.md) (harness only)\n- [project_config.md](project_config.md)\n');
              await writeFile(join(publicDir, 'MEMORY.md'), '# Memory Index\n\n- [project_config.md](project_config.md)\n');

              const snapshot = {
                schemaVersion: 1,
                runId: 'run_delta',
                scopeKey: 'c'.repeat(64),
                contextEnabled: true,
                entries: [{ type: 'message', message: { role: 'user', content: 'Remember that releases use changesets.' } }],
              };
              const snapshotText = JSON.stringify(snapshot, null, 2) + '\n';
              const snapshotFile = join(runDir, 'snapshot.json');
              await writeFile(snapshotFile, snapshotText);
              const snapshotDigest = sha256Digest(snapshotText);
              const manifest = {
                schemaVersion: 1,
                runId: 'run_delta',
                cwd: repo,
                scopeKey: 'c'.repeat(64),
                scopeDigest: 'b'.repeat(64),
                harnessDir: harness,
                publicDir,
                runDir,
                contextEnabled: true,
                contextMode: 'snapshot',
                snapshotPath: snapshotFile,
                snapshotDigest,
                createdAt: new Date(0).toISOString(),
                sourceHashes: {
                  harness: {
                    'MEMORY.md': sha256Digest(await readFile(join(harness, 'MEMORY.md'))),
                    'preference_style.md': sha256Digest(await readFile(join(harness, 'preference_style.md'))),
                    'project_config.md': sha256Digest(await readFile(join(harness, 'project_config.md'))),
                  },
                  public: {
                    'MEMORY.md': sha256Digest(await readFile(join(publicDir, 'MEMORY.md'))),
                    'project_config.md': sha256Digest(await readFile(join(publicDir, 'project_config.md'))),
                  },
                },
              };
              const run = {
                manifest,
                paths: { snapshotFile },
                lockPath: join(root, 'lock'),
                released: false,
                normalization: { repaired: [], removed: [] },
              };
              const delta = {
                kind: 'incremental-memory-plan',
                version: 1,
                schemaVersion: 1,
                runId: manifest.runId,
                scopeKey: manifest.scopeKey,
                scopeDigest: manifest.scopeDigest,
                artifactHash: manifest.snapshotDigest,
                snapshotDigest: manifest.snapshotDigest,
                operations: [{
                  name: 'project_config.md',
                  kind: 'rewrite',
                  classification: 'safe',
                  content: 'The project uses strict mode.\n',
                  observations: [{ path: 'src/config.ts', status: 'found' }],
                }],
                newMemories: [{
                  name: 'release_process.md',
                  kind: 'project',
                  classification: 'safe',
                  content: 'Releases use changesets.\n',
                  evidence: [{ index: 0, quote: 'Remember that releases use changesets.' }],
                }],
              };

              const plan = await expandIncrementalMemoryPlan(run, ['project_config.md', 'preference_style.md'], delta);
              const planPath = join(runDir, 'plan.json');
              await writeFile(planPath, JSON.stringify(plan, null, 2) + '\n');
              const validator = Bun.spawnSync([
                'python3',
                './packages/continual-learning/scripts/validate-consolidate.py',
                '--plan', planPath,
                '--snapshot', snapshotFile,
                '--repo-root', repo,
                '--check=plan',
                '--expected-run-id', manifest.runId,
                '--expected-scope-key', manifest.scopeKey,
                '--expected-scope-digest', manifest.scopeDigest,
                '--expected-artifact-hash', manifest.snapshotDigest,
                '--expected-selected', JSON.stringify(['project_config.md', 'preference_style.md']),
              ], { cwd: process.cwd() });
              const applied = await applyConsolidationPlan(run, plan);
              console.log(JSON.stringify({
                plan,
                validatorExit: validator.exitCode,
                validatorOutput: validator.stdout.toString(),
                applied,
                rewritten: await readFile(join(harness, 'project_config.md'), 'utf8'),
                untouchedPrivate: await readFile(join(harness, 'preference_style.md'), 'utf8'),
                createdPublic: await readFile(join(publicDir, 'release_process.md'), 'utf8'),
              }));
            """,
            {"TEST_ROOT": temporary},
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["validatorExit"] == 0, payload["validatorOutput"]
        plan = payload["plan"]
        assert plan["kind"] == "memory-consolidation-plan"
        assert plan["selected"] == ["project_config.md", "preference_style.md"]
        assert plan["inventory"] == [
            {"name": "project_config.md", "classification": "safe"},
            {"name": "preference_style.md", "classification": "private"},
        ]
        assert plan["clusters"] == [
            {"name": "incremental-selected", "files": ["project_config.md", "preference_style.md"]}
        ]
        assert plan["staleness"] == [
            {"name": "project_config.md", "verdict": "KEEP"},
            {"name": "preference_style.md", "verdict": "KEEP"},
        ]
        grounding = {record["name"]: record for record in plan["grounding"]}
        assert grounding["project_config.md"]["status"] == "VERIFIED"
        assert grounding["project_config.md"]["observations"] == [
            {"path": "src/config.ts", "status": "found"}
        ]
        assert grounding["preference_style.md"]["status"] == "N/A"
        assert len(grounding["preference_style.md"]["reason"]) <= 300
        assert payload["applied"]["selected"] == ["preference_style.md", "project_config.md"]
        assert payload["rewritten"] == "The project uses strict mode.\n"
        assert payload["untouchedPrivate"] == "Prefer concise output.\n"
        assert payload["createdPublic"] == "Releases use changesets.\n"


def test_rejects_foreign_out_of_scope_duplicate_and_invalid_classification() -> None:
    result = run_bun(r"""
      import { mkdir, writeFile } from 'node:fs/promises';
      import { join } from 'node:path';
      import { expandIncrementalMemoryPlan } from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      const root = await Bun.$`mktemp -d`.text().then(value => value.trim());
      const harness = join(root, 'harness');
      await mkdir(harness, { recursive: true });
      await writeFile(join(harness, 'private.md'), 'private\n');
      await writeFile(join(harness, 'safe.md'), 'safe\n');
      await writeFile(join(harness, 'MEMORY.md'), '- [private.md](private.md) (harness only)\n- [safe.md](safe.md)\n');
      const manifest = {
        runId: 'run_scope', scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: 'a'.repeat(64),
        harnessDir: harness, cwd: root, sourceHashes: { harness: {}, public: {} },
      };
      const run = { manifest };
      const base = {
        kind: 'incremental-memory-plan', version: 1, schemaVersion: 1,
        runId: manifest.runId, scopeKey: manifest.scopeKey, scopeDigest: manifest.scopeDigest,
        artifactHash: manifest.snapshotDigest, snapshotDigest: manifest.snapshotDigest,
        operations: [], newMemories: [],
      };
      const capture = async (selected, delta) => {
        try { await expandIncrementalMemoryPlan(run, selected, delta); return null; }
        catch (error) { return error.message; }
      };
      console.log(JSON.stringify({
        foreign: await capture(['safe.md'], { ...base, runId: 'run_foreign' }),
        outside: await capture(['safe.md'], { ...base, operations: [{ name: 'private.md', kind: 'rewrite', classification: 'private', content: 'x\n' }] }),
        duplicateSelected: await capture(['safe.md', 'safe.md'], base),
        duplicateOperation: await capture(['safe.md'], { ...base, operations: [
          { name: 'safe.md', kind: 'rewrite', classification: 'safe', content: 'one\n' },
          { name: 'safe.md', kind: 'rewrite', classification: 'safe', content: 'two\n' },
        ] }),
        override: await capture(['private.md'], { ...base, operations: [{ name: 'private.md', kind: 'rewrite', classification: 'safe', content: 'x\n' }] }),
        invalid: await capture(['safe.md'], { ...base, operations: [{ name: 'safe.md', kind: 'rewrite', classification: 'shared', content: 'x\n' }] }),
      }));
    """)
    assert result.returncode == 0, result.stderr
    errors = json.loads(result.stdout.strip().splitlines()[-1])
    assert "run id mismatch" in errors["foreign"]
    assert "outside selected scope" in errors["outside"]
    assert "duplicate selected" in errors["duplicateSelected"]
    assert "duplicated" in errors["duplicateOperation"]
    assert "classification" in errors["override"]
    assert "classification" in errors["invalid"]


def test_delete_requires_allowed_verdict_and_preservation_still_uses_validator() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-memory-delete-") as temporary:
        result = run_bun(
            r"""
              import { mkdir, writeFile } from 'node:fs/promises';
              import { join } from 'node:path';
              import { expandIncrementalMemoryPlan } from './packages/continual-learning/extensions/incremental-memory-plan.ts';
              const root = process.env.TEST_ROOT;
              const repo = join(root, 'repo');
              const harness = join(root, 'harness');
              await mkdir(join(repo, 'docs'), { recursive: true });
              await mkdir(harness, { recursive: true });
              await writeFile(join(repo, 'docs', 'knowledge.md'), 'preserved knowledge\n');
              await writeFile(join(harness, 'old.md'), 'obsolete\n');
              await writeFile(join(harness, 'MEMORY.md'), '- [old.md](old.md)\n');
              const manifest = {
                runId: 'run_delete', scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: 'a'.repeat(64),
                harnessDir: harness, cwd: repo, sourceHashes: { harness: {}, public: {} },
              };
              const run = { manifest };
              const base = {
                kind: 'incremental-memory-plan', version: 1, schemaVersion: 1,
                runId: manifest.runId, scopeKey: manifest.scopeKey, scopeDigest: manifest.scopeDigest,
                artifactHash: manifest.snapshotDigest, snapshotDigest: manifest.snapshotDigest,
                newMemories: [],
              };
              const capture = async delta => {
                try { return { plan: await expandIncrementalMemoryPlan(run, ['old.md'], delta) }; }
                catch (error) { return { error: error.message }; }
              };
              const missingVerdict = await capture({ ...base, operations: [{ name: 'old.md', kind: 'delete', classification: 'safe', preservedIn: ['docs/knowledge.md'] }] });
              const keepVerdict = await capture({ ...base, operations: [{ name: 'old.md', kind: 'delete', classification: 'safe', verdict: 'KEEP', preservedIn: ['docs/knowledge.md'] }] });
              const missingPreservation = await capture({ ...base, operations: [{ name: 'old.md', kind: 'delete', classification: 'safe', verdict: 'SUPERSEDED' }] });
              const unsafePreservation = await capture({ ...base, operations: [{ name: 'old.md', kind: 'delete', classification: 'safe', verdict: 'SUPERSEDED', preservedIn: ['docs/missing.md'] }] });
              const validShape = await capture({ ...base, operations: [{ name: 'old.md', kind: 'delete', classification: 'safe', verdict: 'SUPERSEDED', preservedIn: ['docs/knowledge.md'] }] });
              const planPath = join(root, 'plan.json');
              await writeFile(planPath, JSON.stringify(validShape.plan, null, 2) + '\n');
              const validator = Bun.spawnSync([
                'python3', './packages/continual-learning/scripts/validate-consolidate.py',
                '--plan', planPath, '--repo-root', repo, '--check=plan',
              ], { cwd: process.cwd() });
              console.log(JSON.stringify({
                missingVerdict, keepVerdict, missingPreservation, unsafePreservation,
                staleness: validShape.plan.staleness,
                validatorExit: validator.exitCode,
                validatorOutput: validator.stdout.toString(),
              }));
            """,
            {"TEST_ROOT": temporary},
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert "allowed explicit staleness verdict" in payload["missingVerdict"]["error"]
        assert "allowed explicit staleness verdict" in payload["keepVerdict"]["error"]
        assert "preservedIn" in payload["missingPreservation"]["error"]
        assert "existing regular file" in payload["unsafePreservation"]["error"]
        assert payload["staleness"] == [{"name": "old.md", "verdict": "SUPERSEDED"}]
        assert payload["validatorExit"] == 0, payload["validatorOutput"]


def test_rejects_unvalidated_repository_observations() -> None:
    with tempfile.TemporaryDirectory(prefix="incremental-memory-grounding-") as temporary:
        result = run_bun(
            r"""
              import { mkdir, writeFile } from 'node:fs/promises';
              import { join } from 'node:path';
              import { expandIncrementalMemoryPlan } from './packages/continual-learning/extensions/incremental-memory-plan.ts';
              const root = process.env.TEST_ROOT;
              const repo = join(root, 'repo');
              const harness = join(root, 'harness');
              await mkdir(join(repo, 'src'), { recursive: true });
              await mkdir(harness, { recursive: true });
              await writeFile(join(repo, 'src', 'real.ts'), 'export {};\n');
              await writeFile(join(harness, 'project_fact.md'), 'fact\n');
              await writeFile(join(harness, 'MEMORY.md'), '- [project_fact.md](project_fact.md)\n');
              const manifest = {
                runId: 'run_grounding', scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: 'a'.repeat(64),
                harnessDir: harness, cwd: repo, sourceHashes: { harness: {}, public: {} },
              };
              const run = { manifest };
              const base = {
                kind: 'incremental-memory-plan', version: 1, schemaVersion: 1,
                runId: manifest.runId, scopeKey: manifest.scopeKey, scopeDigest: manifest.scopeDigest,
                artifactHash: manifest.snapshotDigest, snapshotDigest: manifest.snapshotDigest, newMemories: [],
              };
              const capture = async observations => {
                try {
                  const plan = await expandIncrementalMemoryPlan(run, ['project_fact.md'], { ...base, operations: [{
                    name: 'project_fact.md', kind: 'rewrite', classification: 'safe', content: 'updated\n', observations,
                  }] });
                  return { grounding: plan.grounding };
                } catch (error) { return { error: error.message }; }
              };
              console.log(JSON.stringify({
                valid: await capture([{ path: 'src/real.ts', status: 'found' }]),
                escaping: await capture([{ path: '../outside.ts', status: 'found' }]),
                missing: await capture([{ path: 'src/missing.ts', status: 'found' }]),
                badStatus: await capture([{ path: 'src/real.ts', status: 'maybe' }]),
              }));
            """,
            {"TEST_ROOT": temporary},
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["valid"]["grounding"][0]["status"] == "VERIFIED"
        assert "repository-relative" in payload["escaping"]["error"]
        assert "existing regular file" in payload["missing"]["error"]
        assert "found, missing, or updated" in payload["badStatus"]["error"]
