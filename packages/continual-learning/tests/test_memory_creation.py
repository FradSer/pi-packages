from __future__ import annotations

# --- Merged from test_memory_creation.py ---
"""Contracts for context-derived memory proposals and frozen session input."""


import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from support import PKG_DIR as PACKAGE, initialize_git_repo, run_bun

SCRIPT = PACKAGE / "scripts" / "validate-consolidate.py"


def run_validator(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def write_json(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot(role: str = "user", text: str = "I prefer concise status updates.") -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "runId": "memory-run-1",
        "scopeKey": "c" * 64,
        "contextEnabled": True,
        "entries": [{"type": "message", "message": {"role": role, "content": text}}],
    }


def plan(snapshot_digest: str, proposals: list[dict[str, object]], selected: list[str] | None = None) -> dict[str, object]:
    selected = [] if selected is None else selected
    inventory = [
        {"name": name, "classification": "safe"}
        for name in selected
    ]
    return {
        "kind": "memory-consolidation-plan",
        "version": 1,
        "schemaVersion": 1,
        "runId": "memory-run-1",
        "scopeKey": "c" * 64,
        "scopeDigest": "b" * 64,
        "snapshotDigest": snapshot_digest,
        "artifactHash": snapshot_digest,
        "selected": selected,
        "inventory": inventory,
        "clusters": [{"name": "existing", "files": selected}] if selected else [],
        "staleness": [{"name": name, "verdict": "KEEP"} for name in selected],
        "grounding": [
            {
                "name": name,
                "status": "N/A",
                "reason": "no repository claim",
                "observations": [],
            }
            for name in selected
        ],
        "report": [{"name": name, "status": "KEEP", "summary": "existing"} for name in selected],
        "operations": [],
        "newMemories": proposals,
    }


def proposal(
    name: str = "preference.md",
    kind: str = "preference",
    content: str = "---\ndescription: concise updates\n---\nPrefer concise status updates.\n",
    evidence_text: str = "I prefer concise status updates.",
    index: int = 0,
    classification: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "name": name,
        "kind": kind,
        "content": content,
        "evidence": [{"index": index, "quote": evidence_text}],
    }
    if classification is not None:
        value["classification"] = classification
    return value


def invoke_plan(root: Path, plan_value: dict[str, object], snapshot_value: dict[str, object]) -> subprocess.CompletedProcess[str]:
    snapshot_path = root / "snapshot.json"
    snapshot_raw = write_json(snapshot_path, snapshot_value)
    plan_value["snapshotDigest"] = sha_bytes(snapshot_raw)
    plan_value["artifactHash"] = plan_value["snapshotDigest"]
    plan_path = root / "plan.json"
    write_json(plan_path, plan_value)
    return run_validator([
        "--plan", str(plan_path),
        "--snapshot", str(snapshot_path),
        "--check=plan",
        "--expected-run-id", "memory-run-1",
        "--expected-scope-key", "c" * 64,
        "--expected-scope-digest", "b" * 64,
        "--expected-artifact-hash", plan_value["artifactHash"],
        "--expected-selected", json.dumps(plan_value["selected"]),
    ])


def test_empty_existing_scope_accepts_user_evidenced_new_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        snapshot_value = snapshot()
        snapshot_raw = json.dumps(snapshot_value, ensure_ascii=False, indent=2).encode() + b"\n"
        result = invoke_plan(root, plan(sha_bytes(snapshot_raw), [proposal()]), snapshot_value)
        assert result.returncode == 0, result.stdout
        details = json.loads(result.stdout)["details"]
        assert details["newMemoryCount"] == 1


def test_new_memory_description_accepts_the_shared_bound_and_rejects_oversize() -> None:
    # Given generated Memory carrying several supported facts,
    # When the description is within the 400 code-unit bound,
    # Then the parent validator accepts the complete claim;
    # And a longer description is rejected instead of truncated.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        snapshot_value = snapshot()
        snapshot_raw = json.dumps(snapshot_value, ensure_ascii=False, indent=2).encode() + b"\n"
        at_bound = "Prefer concise status updates. " * 12
        assert len(at_bound) <= 400
        accepted = invoke_plan(
            root,
            plan(sha_bytes(snapshot_raw), [proposal(content=f"---\ndescription: {at_bound}\n---\nPrefer concise status updates.\n")]),
            snapshot_value,
        )
        assert accepted.returncode == 0, accepted.stdout
        oversized = "Prefer concise status updates. " * 13
        rejected = invoke_plan(
            root,
            plan(sha_bytes(snapshot_raw), [proposal(content=f"---\ndescription: {oversized}\n---\nPrefer concise status updates.\n")]),
            snapshot_value,
        )
        assert rejected.returncode == 1
        assert "memory_bounds" in rejected.stdout and "400" in rejected.stdout
        assert "description" in rejected.stdout


def test_new_memory_rejects_assistant_only_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(root, plan("a" * 64, [proposal(evidence_text="The user prefers concise updates.")]), snapshot("assistant", "The user prefers concise updates."))
        assert result.returncode == 1
        assert "context_evidence" in result.stdout


def test_new_memory_rejects_sensitive_content_or_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(content="api_key = sk-test-secret\n")]),
            snapshot(text="The preference is concise updates."),
        )
        assert result.returncode == 1
        assert "sensitive" in result.stdout
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(content="Prefer concise updates.\n", evidence_text="token: sk-test-secret")]),
            snapshot(text="token: sk-test-secret"),
        )
        assert result.returncode == 1
        assert "sensitive" in result.stdout


def test_preference_cannot_be_marked_safe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(classification="safe")]),
            snapshot(),
        )
        assert result.returncode == 1
        assert "privacy" in result.stdout


def test_new_memory_scope_cannot_overlap_existing_selected_names() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = invoke_plan(
            root,
            plan("a" * 64, [proposal(name="project.md", kind="project", evidence_text="The project uses TypeScript.")], ["project.md"]),
            snapshot(text="The project uses TypeScript."),
        )
        assert result.returncode == 1
        assert "new memory" in result.stdout


def test_new_memory_writes_empty_existing_scope_transactionally() -> None:
    result = run_bun(
        """
        import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
        import { join } from 'node:path';
        import { createHash } from 'node:crypto';
        import { applyConsolidationPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const root = await mkdtemp('/tmp/pi-memory-new-');
        const harness = join(root, 'harness');
        const publicDir = join(root, 'public');
        const snapshot = { schemaVersion: 1, runId: 'run_test', scopeKey: 'c'.repeat(64), contextEnabled: true,
          entries: [{ type: 'message', message: { role: 'user', content: 'I prefer concise updates.' } }] };
        const snapshotText = JSON.stringify(snapshot, null, 2) + "\\n";
        const snapshotFile = join(root, 'snapshot.json');
        await writeFile(snapshotFile, snapshotText);
        const digest = createHash('sha256').update(snapshotText).digest('hex');
        const run = { manifest: { runId: 'run_test', scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: digest,
          harnessDir: harness, publicDir, sourceHashes: { harness: {}, public: {} } },
          paths: { snapshotFile }, released: false };
        const applied = await applyConsolidationPlan(run, {
          runId: 'run_test', scopeDigest: 'b'.repeat(64), artifactHash: digest, selected: [],
          newMemories: [{ name: 'preference.md', kind: 'preference', content: 'Prefer concise updates.\\n',
            evidence: [{ index: 0, quote: 'I prefer concise updates.' }] }],
        });
        console.log(JSON.stringify({ applied, harness: await readFile(join(harness, 'preference.md'), 'utf8'),
          publicExists: await Bun.file(join(publicDir, 'preference.md')).exists() }));
        """
    )
    assert result["applied"]["created"] == ["preference.md"]
    assert result["harness"] == "Prefer concise updates.\n"
    assert result["publicExists"] is False


def test_project_new_memory_defaults_safe_and_mirrors_to_public_root() -> None:
    result = run_bun(
        """
        import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
        import { join } from 'node:path';
        import { createHash } from 'node:crypto';
        import { applyConsolidationPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const root = await mkdtemp('/tmp/pi-memory-project-');
        const harness = join(root, 'harness');
        const publicDir = join(root, 'public');
        const snapshot = { schemaVersion: 1, runId: 'run_project', scopeKey: 'c'.repeat(64), contextEnabled: true,
          entries: [{ type: 'message', message: { role: 'toolResult', content: 'The project uses TypeScript.' } }] };
        const snapshotText = JSON.stringify(snapshot, null, 2) + "\\n";
        const snapshotFile = join(root, 'snapshot.json');
        await writeFile(snapshotFile, snapshotText);
        const digest = createHash('sha256').update(snapshotText).digest('hex');
        const run = { manifest: { runId: 'run_project', scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: digest,
          harnessDir: harness, publicDir, sourceHashes: { harness: {}, public: {} } },
          paths: { snapshotFile }, released: false };
        const applied = await applyConsolidationPlan(run, {
          runId: 'run_project', scopeDigest: 'b'.repeat(64), artifactHash: digest, selected: [],
          newMemories: [{ name: 'project.md', kind: 'project', content: 'The project uses TypeScript.\\n',
            evidence: [{ index: 0, quote: 'The project uses TypeScript.' }] }],
        });
        console.log(JSON.stringify({ applied, harness: await readFile(join(harness, 'project.md'), 'utf8'),
          public: await readFile(join(publicDir, 'project.md'), 'utf8'),
          publicIndex: await readFile(join(publicDir, 'MEMORY.md'), 'utf8') }));
        """
    )
    assert result["applied"]["created"] == ["project.md"]
    assert result["harness"] == result["public"] == "The project uses TypeScript.\n"
    assert "(harness only)" not in result["publicIndex"]


def test_parent_rejects_an_oversized_generated_description_before_any_write() -> None:
    # Given a fresh proposal whose frontmatter description exceeds the shared bound,
    # When the parent validates and applies the plan,
    # Then the plan is refused with a 400 code-unit diagnostic and no file is written;
    # And a description within the bound is accepted.
    result = run_bun(
        r'''
        import { mkdtemp, readFile, writeFile, access } from 'node:fs/promises';
        import { join } from 'node:path';
        import { createHash } from 'node:crypto';
        import { applyConsolidationPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const claim = 'Run pnpm test --filter continual-learning for this package; run it before reporting package changes complete.';
        const setup = async (runId) => {
          const root = await mkdtemp('/tmp/pi-memory-description-');
          const harness = join(root, 'harness');
          const publicDir = join(root, 'public');
          const snapshot = { schemaVersion: 1, runId, scopeKey: 'c'.repeat(64), contextEnabled: true,
            entries: [{ type: 'message', message: { role: 'user', content: 'Use pnpm test --filter continual-learning for this package.' } }] };
          const snapshotText = JSON.stringify(snapshot, null, 2) + "\n";
          const snapshotFile = join(root, 'snapshot.json');
          await writeFile(snapshotFile, snapshotText);
          const digest = createHash('sha256').update(snapshotText).digest('hex');
          const run = { manifest: { runId, scopeKey: 'c'.repeat(64), scopeDigest: 'b'.repeat(64), snapshotDigest: digest,
            harnessDir: harness, publicDir, sourceHashes: { harness: {}, public: {} } },
            paths: { snapshotFile }, released: false };
          const plan = (description) => ({ runId, scopeDigest: 'b'.repeat(64), artifactHash: digest, selected: [],
            newMemories: [{ name: 'verification.md', kind: 'project', classification: 'safe',
              content: `---\ndescription: ${description}\ntype: project\n---\n${claim}\n`,
              evidence: [{ index: 0, quote: 'Use pnpm test --filter continual-learning for this package.' }] }] });
          return { run, plan, harness };
        };
        const good = await setup('run_description_ok');
        const accepted = await applyConsolidationPlan(good.run, good.plan(`${claim} ${claim} ${claim}`));
        const bad = await setup('run_description_oversize');
        let rejected = '';
        try { await applyConsolidationPlan(bad.run, bad.plan(`expanded context ${'x'.repeat(500)}`)); } catch (error) { rejected = error.message; }
        let wrote = true;
        try { await access(join(bad.harness, 'verification.md')); } catch { wrote = false; }
        console.log(JSON.stringify({ accepted: accepted.created, body: await readFile(join(good.harness, 'verification.md'), 'utf8'), rejected, wrote }));
        '''
    )
    assert result["accepted"] == ["verification.md"]
    assert "description" in result["body"]
    assert "400 UTF-16 code units" in result["rejected"]
    assert result["wrote"] is False


def test_snapshot_session_context_is_immutable_but_preserves_method_binding() -> None:
    result = run_bun(
        """
        import { snapshotSessionContext } from './packages/continual-learning/extensions/consolidation-run.ts';
        const manager = {
          branch: [{ role: 'user', content: 'before' }],
          context: [{ role: 'user', content: 'context before' }],
          marker: 'manager',
          cwd: 'before-cwd',
          sessionId: 'before-session',
          sessionFile: 'before-session.jsonl',
          header: { id: 'before-session', cwd: 'before-cwd' },
          getBranch() { return this.branch; },
          buildContextEntries() { return this.context; },
          markerFromThis() { return this.marker; },
          getCwd() { return this.cwd; },
          getSessionId() { return this.sessionId; },
          getSessionFile() { return this.sessionFile; },
          getHeader() { return this.header; },
        };
        const context = { cwd: 'before-cwd', sessionManager: manager };
        const frozen = snapshotSessionContext(context);
        manager.branch[0].content = 'after';
        manager.context.push({ role: 'user', content: 'later' });
        manager.cwd = 'after-cwd';
        manager.sessionId = 'after-session';
        manager.sessionFile = 'after-session.jsonl';
        manager.header.cwd = 'after-cwd';
        context.cwd = 'after-cwd';
        console.log(JSON.stringify({
          branch: frozen.sessionManager.getBranch(),
          context: frozen.sessionManager.buildContextEntries(),
          bound: frozen.sessionManager.markerFromThis(),
          cwd: frozen.cwd,
          sessionCwd: frozen.sessionManager.getCwd(),
          sessionId: frozen.sessionManager.getSessionId(),
          sessionFile: frozen.sessionManager.getSessionFile(),
          header: frozen.sessionManager.getHeader(),
          frozen: Object.isFrozen(frozen.sessionManager.getBranch()) && Object.isFrozen(frozen.sessionManager.getBranch()[0]),
        }));
        """
    )
    assert result == {
        "branch": [{"role": "user", "content": "before"}],
        "context": [{"role": "user", "content": "context before"}],
        "bound": "manager",
        "cwd": "before-cwd",
        "sessionCwd": "before-cwd",
        "sessionId": "before-session",
        "sessionFile": "before-session.jsonl",
        "header": {"id": "before-session", "cwd": "before-cwd"},
        "frozen": True,
    }


def test_loader_budget_counts_metadata_instead_of_memory_bodies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        memory = repo / ".memory"
        agent = root / "agent"
        memory.mkdir(parents=True)
        initialize_git_repo(repo)
        (memory / "a.md").write_text("x" * 5_000, encoding="utf-8")
        (memory / "b.md").write_text("y" * 5_000, encoding="utf-8")
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ loadAndDeduplicateMemories }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            console.log(JSON.stringify(await loadAndDeduplicateMemories({json.dumps(str(repo))}, {{ maxTotalChars: 1_000 }})));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert [entry["filename"] for entry in result["entries"]] == ["a.md", "b.md"]


def test_private_memory_exposes_its_root_and_entry_filename() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        initialize_git_repo(repo)
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ resolveMemoryPaths }} = await import('./packages/continual-learning/extensions/memory-paths.ts');
            const {{ loadAndDeduplicateMemories, formatMemoriesBlock }} = await import('./packages/continual-learning/extensions/memory-files.ts');
            const {{ mkdir, writeFile }} = await import('node:fs/promises');
            const memory = resolveMemoryPaths({json.dumps(str(repo))});
            await mkdir(memory.harnessDir, {{ recursive: true }});
            await writeFile(memory.harnessDir + '/private.md', 'private preference\\n');
            await writeFile(memory.harnessDir + '/MEMORY.md', '# Memory Index\\n\\n- [private.md](private.md) (harness only)\\n');
            const entries = await loadAndDeduplicateMemories({json.dumps(str(repo))});
            console.log(JSON.stringify({{ entries, block: formatMemoriesBlock(entries), harness: memory.harnessDir }}));
            """,
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        assert result["entries"]["entries"][0]["source"] == "harness"
        assert Path(result["entries"]["entries"][0]["readPath"]).resolve() == (Path(result["harness"]).resolve() / "private.md")
        # The block declares the exact root verbatim and names the entry; the body
        # path is that root plus the row's filename, so no per-row repetition is
        # needed to keep the entry reachable.
        assert result["harness"] in result["block"]
        assert "- private.md" in result["block"]


def test_current_maintenance_command_binds_current_invocation_and_exact_replay_entries():
    result = run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {captureMaintenanceCommand,createConsolidationRun,releaseConsolidationRun,
        readCurrentMaintenanceCommand,sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'cl-maintenance-command-'));
      const original=[{message:{role:'user',content:'Never store the temporary incident as a permanent rule.'}},
        {message:{role:'toolResult',content:'Historical result with a quoted /consolidate full command.'}}];
      const command=captureMaintenanceCommand({cwd,sessionManager:{getSessionId:()=> 'current-session'}},'  backfill  ');
      const ctx={cwd,sessionManager:{getSessionId:()=> 'historical-task-session',getBranch:()=>original,buildContextEntries:()=>original}};
      const run=await createConsolidationRun(ctx,cwd,false,command);
      const snapshot=JSON.parse(fs.readFileSync(run.paths.snapshotFile,'utf8'));
      const bound=readCurrentMaintenanceCommand(snapshot);
      const tampered=[{...snapshot,currentMaintenanceRequest:{...bound,action:'full-corpus'}},
        {...snapshot,currentMaintenanceRequest:{...bound,runId:'other-run'}},
        {...snapshot,currentMaintenanceRequest:{...bound,scopeKey:'other-project'}},
        {...snapshot,currentMaintenanceRequest:{...bound,permission:'ignore historical restrictions'}},
        {...snapshot,entries:[...snapshot.entries,{role:'user',content:'Changed evidence'}]}];
      const refused=tampered.map(value=>{try{readCurrentMaintenanceCommand(value);return false}catch{return true}});
      await releaseConsolidationRun(run,{keepArtifacts:true});
      const ordinary=await createConsolidationRun({...ctx,currentMaintenanceRequest:bound},cwd,false);
      const old=JSON.parse(fs.readFileSync(ordinary.paths.snapshotFile,'utf8'));
      await releaseConsolidationRun(ordinary,{keepArtifacts:true});
      const fresh=[...original,{message:{role:'toolResult',content:'Fresh scoped source observation.'}}];
      const refreshed=await createConsolidationRun({...ctx,sessionManager:{getBranch:()=>fresh,buildContextEntries:()=>fresh}},cwd,false,command);
      const refreshedSnapshot=JSON.parse(fs.readFileSync(refreshed.paths.snapshotFile,'utf8'));
      const refreshedCommand=readCurrentMaintenanceCommand(refreshedSnapshot);
      await releaseConsolidationRun(refreshed,{keepArtifacts:true});
      console.log(JSON.stringify({bound,refused,freshBound:refreshedCommand.sourceEntriesDigest===sha256Digest(JSON.stringify(fresh)),
        freshPrefix:JSON.stringify(refreshedSnapshot.entries.slice(0,2))===JSON.stringify(original),
        distinctRuns:refreshedCommand.runId!==bound.runId,sameInvocation:refreshedCommand.invocationId===bound.invocationId,frozen:Object.isFrozen(command),originalUnchanged:JSON.stringify(snapshot.entries)===JSON.stringify(original),
        digest:sha256Digest(JSON.stringify(original)),snapshotHashMatches:sha256Digest(fs.readFileSync(run.paths.snapshotFile,'utf8'))===run.manifest.snapshotDigest,
        quotedOrHistoricalPromoted:!!old.currentMaintenanceRequest}));
      fs.rmSync(cwd,{recursive:true,force:true});
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert result['originalUnchanged'] and result['frozen'] and result['snapshotHashMatches']
    assert result['bound']['sessionId'] == 'current-session'
    assert result['bound']['action'] == 'backfill' and result['bound']['arguments'] == '  backfill  '
    assert result['bound']['sourceEntriesDigest'] == result['digest']
    assert all(result['refused']) and not result['quotedOrHistoricalPromoted']
    assert result['freshBound'] and result['freshPrefix'] and result['distinctRuns'] and result['sameInvocation']


# --- Merged from test_combined_memory_amendment.py ---
import pytest
from support import isolated_run_bun


def test_combined_repair_binds_existing_and_new_proposals_without_transcribing_intent() -> None:
    """Given held proposed+retained claims, When ID patches arrive, Then identity stays parent-owned."""
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let next,payload,prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async options=>{prompt=options.prompt;payload=JSON.parse(options.prompt.split('\n').at(-1));return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false,usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:.01}}}}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a'};
      const content=body=>'---\nname: claim\ndescription: Current claim\ntype: project\n---\n'+body;
      const evidence=[{index:0,quote:'Verified current implementation.'}];
      const old={name:'old.md',kind:'rewrite',classification:'private',content:content('Old proposed body.'),evidence};
      const fresh={name:'new.md',kind:'project',classification:'safe',content:content('New proposed body.'),evidence};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[old],newMemories:[fresh]};
      const retained={name:'retained.md',kind:'rewrite',classification:'private',content:content('Corrected retained body.'),evidence};
      const input={identity,rejectedPlan:original,selectedNames:['old.md','retained.md'],retainedRepairNames:['retained.md'],repairableNames:['old.md','new.md'],repairableFields:{'old.md':['body'],'new.md':['body']},errors:['held proposed and retained fields'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Verified current implementation.'}]},existingMemories:[{...old,type:'project',description:'Current claim'},{...retained,type:'project',description:'Current claim',content:content('Old retained body.')}]}};
      const ids=semanticMemoryRepairCandidates(original,input.repairableNames);const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:ids.map(c=>({candidateId:c.candidateId,content:content('Corrected '+c.name+' body.'),evidence})),operations:[retained]};
      next=amendment;const good=await repairIncrementalMemoryPlan(input);const supplied=payload.repairCandidates;const exampleStart=prompt.indexOf('{\n  "kind": "incremental-memory-amendment"');const examples=[JSON.parse(prompt.slice(exampleStart,prompt.indexOf("\n}",exampleStart)+2))];
      const bad=[];
      for(const mutate of [a=>a.replacements[0].candidateId+='stale',a=>a.replacements.push(a.replacements[0]),a=>a.replacements[0].kind='rewrite',a=>a.replacements[0].classification='safe',a=>a.operations[0].name='outside.md',a=>a.operations[0].classification='safe',a=>a.replacements.pop(),a=>a.operations=[],a=>a.operations.push(a.operations[0]),a=>{a.replacements.shift();a.operations.push({...old,content:content('Corrected old.md body.')})},a=>a.newMemories=[]]){next=structuredClone(amendment);mutate(next);bad.push(await repairIncrementalMemoryPlan(input));}
      next={...amendment,replacements:[],operations:[]};const refusal=await repairIncrementalMemoryPlan(input);
      next={...amendment,scopeDigest:'foreign',replacements:[],operations:[]};const foreignRefusal=await repairIncrementalMemoryPlan(input);
      const deleted={name:'obsolete.md',kind:'delete',classification:'private',verdict:'SUBSUMED',preservedIn:['retained.md'],evidence};
      const deletionOriginal={...original,operations:[deleted]};const deletionInput={...input,rejectedPlan:deletionOriginal,selectedNames:['obsolete.md','retained.md'],repairableNames:['obsolete.md','new.md'],repairableFields:{'obsolete.md':['body'],'new.md':['body']}};
      const deletionIds=semanticMemoryRepairCandidates(deletionOriginal,deletionInput.repairableNames);
      next={...amendment,replacements:deletionIds.map(c=>({candidateId:c.candidateId,...(c.contentAllowed?{content:content('Corrected '+c.name+' body.')}:{}),evidence}))};
      await repairIncrementalMemoryPlan(deletionInput);const deleteStart=prompt.indexOf('{\n  "kind": "incremental-memory-amendment"');const deletionExample=JSON.parse(prompt.slice(deleteStart,prompt.indexOf("\n}",deleteStart)+2));
      const retainedOriginal={...original,operations:[],newMemories:[]};next={...retainedOriginal,operations:[retained]};
      const retainedOnly=await repairIncrementalMemoryPlan({...input,rejectedPlan:retainedOriginal,repairableNames:undefined,repairableFields:undefined});
      const retainedStart=prompt.indexOf('{\n  "kind": "incremental-memory-plan"');const retainedExample=JSON.parse(prompt.slice(retainedStart,prompt.indexOf("\n}",retainedStart)+2));
      // Exact real failure family: a newly proposed Memory is regenerated as an
      // existing rewrite, sometimes also duplicated in newMemories. Never coerce it.
      next={...original,operations:[old,retained,{...fresh,kind:'rewrite'}],newMemories:[fresh]};const misplaced=await repairIncrementalMemoryPlan(input);
      console.log(JSON.stringify({good,supplied,examples,ids,bad,misplaced,old,fresh,retained,refusal,foreignRefusal,deletionExample,deletionIds,retainedOnly,retainedExample}));
    ''')
    assert value['good']['outcome'] == 'repaired'
    plan = value['good']['plan']
    assert len(plan['operations']) == 2 and len(plan['newMemories']) == 1
    assert plan['operations'][0]['name'] == 'old.md'
    assert plan['operations'][0]['kind'] == 'rewrite'
    assert plan['operations'][0]['classification'] == 'private'
    assert plan['newMemories'][0]['name'] == 'new.md'
    assert plan['newMemories'][0]['kind'] == 'project'
    assert plan['newMemories'][0]['classification'] == 'safe'
    assert 'Corrected new.md body.' in plan['newMemories'][0]['content']
    assert plan['operations'][1] == value['retained']
    assert [{k:v for k,v in c.items() if k!='reuseOriginalEvidence'} for c in value['supplied']] == value['ids']
    assert all(c['reuseOriginalEvidence'] is False for c in value['supplied'])  # This legacy synthetic snapshot has no bound digest.
    assert all(row['outcome'] == 'failed' for row in value['bad'])
    assert value['misplaced']['outcome'] == 'failed'
    assert value['misplaced']['failureKind'] == 'intent'

    assert len(value['examples']) == 1
    example = value['examples'][0]
    assert [op['name'] for op in example['operations']] == ['retained.md']
    assert example['operations'][0]['kind'] == 'rewrite'
    assert example['operations'][0]['classification'] == 'private'
    assert [patch['candidateId'] for patch in example['replacements']] == [c['candidateId'] for c in value['ids']]

    assert value['bad'][7]['failureKind'] == 'no-correction'
    assert value['refusal']['outcome'] == 'failed' and value['refusal']['failureKind'] == 'no-correction'
    assert value['refusal']['usage']['cost'] == 0.01
    assert value['foreignRefusal']['outcome'] == 'failed' and value['foreignRefusal']['failureKind'] == 'intent'
    delete_patch = next(patch for patch in value['deletionExample']['replacements'] if patch['candidateId'] == value['deletionIds'][0]['candidateId'])
    assert 'content' not in delete_patch, 'A deletion may repair citations but must not acquire a body or change kind'
    assert value['retainedOnly']['outcome'] == 'repaired'
    assert [op['name'] for op in value['retainedExample']['operations']] == ['retained.md']
    assert value['retainedExample']['newMemories'] == []


@pytest.mark.parametrize('native', [False, True])
def test_retained_evidence_only_repair_preserves_frozen_real_contract(tmp_path, native) -> None:
    """Given V89's retyping error, When evidence alone changes, Then reuse exact prior bytes."""
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import {spawnSync} from 'node:child_process';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kit=await import('./packages/kit/src/index.ts');let next,mutate=()=>{},payload,args,nativeEnabled=NATIVE,nativeCalls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async options=>{
        payload=JSON.parse(options.prompt.split('\n').at(-1));args=options.extraArgs;mutate();
        if(nativeEnabled){
          const cli=path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');
          const version=spawnSync('node',[cli,'--version'],{encoding:'utf8'});if(version.status!==0||version.stdout.trim()!=='1.5.0')throw Error('Pi1.5 required');
          const response=structuredClone(next);
          if(response.replacements)response.replacements=response.replacements.map(patch=>{
            const candidate=payload.repairCandidates.find(c=>c.candidateId===patch.candidateId);
            const {candidateId,...rest}=patch;return {...rest,candidateRef:candidate.candidateRef};
          });
          const r=spawnSync('node',[cli,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
            '--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','--bound-candidate-response',JSON.stringify(response),options.prompt],
            {cwd:ROOT,env:{PATH:process.env.PATH,HOME:ROOT,PI_CODING_AGENT_DIR:path.join(ROOT,'agent'),PI_OFFLINE:'1'},encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
          fs.writeFileSync(path.join(ROOT,'native-retained-'+(++nativeCalls)+'.jsonl'),r.stdout);
          if(r.status!==0)throw Error(r.stderr+'\n'+r.stdout);
          return {...kit.parsePiWorkerOutput(r.stdout),exitCode:0,stderr:'',cancelled:false};
        }
        return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false,usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:.1}};
      }}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {learningOutputSchema}=await import('./packages/continual-learning/extensions/planner-output-schema.ts');
      const real=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-retained-and-proposed-repair.json','utf8')).retainedBodyRetyping;
      const snapshot={contextEnabled:true,runId:'r',scopeKey:'s',scopeDigest:'d',entries:[{role:'toolResult',content:'readonly rejectOnClear?: boolean;'}]};
      const h=sha256Digest(JSON.stringify(snapshot,null,2)+'\n'),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:h,snapshotDigest:h};
      const evidence=[{ref:'e0.b0.l1'}],name='limit_function_contract.md';
      const prior={name,classification:'private',type:'project',description:'Declared contract',content:real.predecessor};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]};
      const input={identity,rejectedPlan:original,selectedNames:[name],retainedRepairNames:[name],errors:['source support held'],semanticContext:{frozenEvidence:snapshot,existingMemories:[prior]}};
      const reply={...original,operations:[{name,kind:'rewrite',classification:'private',evidence}]};
      next=reply;const good=await repairIncrementalMemoryPlan(input),contract=payload.retainedOperationContract,nativeArgs=args;
      nativeEnabled=false;const bad=[];
      for(const change of [v=>v.operations[0].content=null,v=>v.operations[0].content='',v=>v.operations[0].content=42,
        v=>v.runId='foreign',v=>delete v.artifactHash,v=>delete v.kind,v=>v.version=2,v=>v.schemaVersion=2,
        v=>v.operations[0].classification='safe',v=>v.operations.push(v.operations[0]),v=>v.operations[0].contentSha256='forged',v=>v.operations[0].foreign=true,
        v=>v.operations[0].evidence=[{ref:'e0.b0.l9'}]]){
        next=structuredClone(reply);change(next);bad.push(await repairIncrementalMemoryPlan(input));
      }
      for(const changes of [{requiredTextChanges:{[name]:['body']}},{requiredTextChanges:{[name]:['description']}},
        {semanticContext:{...input.semanticContext,frozenEvidence:{...snapshot,runId:'foreign'}}},
        {semanticContext:{...input.semanticContext,existingMemories:[prior,prior]}}]){
        next=reply;bad.push(await repairIncrementalMemoryPlan({...input,...changes}));
      }
      // Confirmed retained-body contradictions require a body correction, not
      // a copied predecessor or a changed description. Unknown holds may still
      // use the existing evidence-only path; no claim is forced to change.
      const requiredBody=[];
      for(const mode of ['same-body','description-only','trailing-newline','outer-blanklines','crlf-only','description-plus-whitespace','bom-description-only','bom-body','body']){
        if(mode.startsWith('bom-'))prior.content='\uFEFF'+real.predecessor;
        let content=prior.content;
        if(mode==='description-only')content=content.replace(/description:[^\n]*/, 'description: Revised discovery text');
        if(mode==='trailing-newline')content+='\n';
        if(mode==='outer-blanklines')content=content.replace(/(\n---\n)/, '$1\n\n')+'\n\n';
        if(mode==='crlf-only')content=content.replaceAll('\n','\r\n');
        if(mode==='description-plus-whitespace')content=content.replace(/description:[^\n]*/, 'description: Revised discovery text')+'\n';
        if(mode==='bom-description-only')content=content.replace(/description:[^\n]*/, 'description: Revised discovery text');
        if(mode==='body'||mode==='bom-body')content+='\nChanged source condition.\n';
        next={...reply,operations:[{...reply.operations[0],content}]};
        nativeEnabled=NATIVE&&mode.startsWith('bom-');
        const result=await repairIncrementalMemoryPlan({...input,requiredTextChanges:{[name]:['body']}});
        requiredBody.push({mode,outcome:result.outcome,failureKind:result.failureKind,hasPlan:!!result.plan,cost:result.usage?.cost,native:nativeEnabled});
        nativeEnabled=false;
        prior.content=real.predecessor;
      }
      next=reply;mutate=()=>{prior.content=real.rejectedReplacement};const changed=await repairIncrementalMemoryPlan(input);prior.content=real.predecessor;mutate=()=>{};
      next=reply;mutate=()=>{snapshot.entries[0].content='changed after generation'};const sourceChanged=await repairIncrementalMemoryPlan(input);snapshot.entries[0].content='readonly rejectOnClear?: boolean;';mutate=()=>{};
      next=reply;mutate=()=>{input.requiredTextChanges={[name]:['body']}};const textRequirementChanged=await repairIncrementalMemoryPlan(input);delete input.requiredTextChanges;mutate=()=>{};
      next=reply;mutate=()=>{original.newMemories.push({name:'race.md'})};const proposalChanged=await repairIncrementalMemoryPlan(input);original.newMemories=[];mutate=()=>{};
      const fresh={name:'failure.md',kind:'project',classification:'private',content:'---\nname: failure\ndescription: Observed failure\ntype: project\n---\nThe observed task failed.',evidence};
      const combinedOriginal={...original,newMemories:[fresh]},ids=semanticMemoryRepairCandidates(combinedOriginal,['failure.md']);
      next={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:ids[0].candidateId,evidence}],operations:reply.operations};
      nativeEnabled=NATIVE;const combined=await repairIncrementalMemoryPlan({...input,rejectedPlan:combinedOriginal,repairableNames:['failure.md'],repairableFields:{'failure.md':['body']}});
      next={...next,replacements:[{candidateId:ids[0].candidateId,description:'Observed verification failure',evidence}]};
      const atomicDescription=await repairIncrementalMemoryPlan({...input,rejectedPlan:combinedOriginal,repairableNames:['failure.md'],repairableFields:{'failure.md':['description']},atomicBodyEvidence:true});
      const delta=learningOutputSchema('memory-delta'),retained=learningOutputSchema('memory-retained-amendment');
      console.log(JSON.stringify({good,bad,requiredBody,changed,sourceChanged,textRequirementChanged,proposalChanged,combined,atomicDescription,fresh,contract,nativeArgs,nativeCalls,originalUnchanged:original.operations.length===0,
        predecessorUnchanged:prior.content===real.predecessor,body:real.predecessor,
        deltaContentRequired:delta.properties.operations.items.anyOf[0].required.includes('content'),
        retainedContentOptional:retained&&!retained.properties.operations.items.anyOf[0].required.includes('content')}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE', str(native).lower()))
    assert result['good']['outcome'] == 'repaired', result['good']
    for row in result['requiredBody']:
        assert row.get('cost') in (0, None) if row['native'] else row['cost'] == .1, row
        if row['mode'] in ('body', 'bom-body'):
            assert row['outcome'] == 'repaired' and row['hasPlan'], row
        else:
            assert row['outcome'] == 'failed' and row['failureKind'] == 'no-correction' and not row['hasPlan'], row
    operation = result['good']['plan']['operations'][0]
    assert operation['content'] == result['body']
    assert operation['evidence'] == [{'index': 0, 'quote': 'readonly rejectOnClear?: boolean;'}]
    assert result['contract']['records'][0]['reuseFrozenContent'] is True
    assert result['retainedContentOptional'] and result['deltaContentRequired']
    assert all(row['outcome'] == 'failed' for row in result['bad']), result['bad']
    assert all(result[name]['outcome'] == 'failed' for name in ['changed', 'sourceChanged', 'textRequirementChanged', 'proposalChanged'])
    assert result['combined']['outcome'] == 'repaired', result['combined']
    assert result['combined']['plan']['operations'][0]['content'] == result['body']
    assert result['atomicDescription']['outcome'] == 'repaired', result['atomicDescription']
    assert result['atomicDescription']['plan']['newMemories'][0]['content'] == result['fresh']['content'].replace('description: Observed failure', 'description: Observed verification failure')
    assert result['atomicDescription']['plan']['operations'][0]['content'] == result['body']
    assert result['originalUnchanged'] and result['predecessorUnchanged']

    assert result['nativeCalls'] == (5 if native else 0)


# --- Merged from test_command_surface_retirement.py ---
"""Phase 4: one documented command entry and a retired worker tool surface."""

import json

from support import PKG_DIR, run_bun


def test_runtime_diagnostics_do_not_tell_users_to_type_an_old_command() -> None:
    # A user who hits a Memory write guard, a headless menu, or a status view
    # must be pointed at /learning, never at a retired /memory, /consolidate or
    # /harness command. Frozen fixtures under tests/fixtures/** keep their
    # historical strings byte-identical and are intentionally excluded here.
    retired = ("Use /memory", "Use /consolidate", "Use /harness",
               "type /memory", "type /consolidate", "type /harness")
    offenders: list[str] = []
    for path in (PKG_DIR / "extensions").glob("*.ts"):
        text = path.read_text(encoding="utf-8")
        for phrase in retired:
            if phrase in text:
                offenders.append(f"{path.name}: {phrase}")
    assert offenders == [], offenders


def _inject_source() -> str:
    return (PKG_DIR / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")


def test_learning_menu_harness_branch_uses_the_direct_procedure_bridge() -> None:
    # Given /harness is no longer a registered command, When a user chooses
    # Manage Harness rules in /learning, Then the menu opens the guarded
    # procedure through the same bridge the learn tool uses, instead of
    # looking up a command or telling the user to type /harness.
    source = _inject_source()
    menu = source.split("const openLearningMenu", 1)[1].split("pi.registerCommand(\"learning\"", 1)[0]
    assert "getCommands().find" not in menu
    assert 'name === "harness"' not in menu
    assert "Use /harness" not in menu
    assert " ".join(menu.split()).count("startHarnessProcedureForLearn(") == 1
    assert "Harness rules are unavailable" not in menu


def test_only_learning_is_exposed_to_users() -> None:
    # Phase 4 retires the old *user* command surface: the model guidance and
    # the single documented entry name only /learning. Three legacy command
    # registrations (/memory, /consolidate in inject-memory.ts; /harness in
    # guardrails.ts) deliberately survive as internal frozen-provenance and
    # offline-E2E bindings -- they are never offered in a menu, never named by
    # guidance, and never documented as user input. See HANDOFF.md for the
    # exact completion-gate and frozen-proof consumers that require them.
    source = _inject_source()
    assert 'pi.registerCommand("learning"' in source
    for guidance in (
        "AGENT_LEARNING_TOOL_GUIDANCE",
        "SETTLED_LEARNING_GUIDANCE",
    ):
        block = source.split(guidance, 1)[1].split("`;", 1)[0]
        assert "/memory" not in block and "/consolidate" not in block, guidance
        assert "/harness" not in block, guidance
    # The model guidance must steer to learn without naming retired commands.
    tool_description = source.split("name: AGENT_MEMORY_TOOL", 1)[1].split("async execute", 1)[0]
    assert "/memory" not in tool_description and "/consolidate" not in tool_description
    assert "/harness" not in tool_description
    assert "learn" in tool_description


def test_internal_frozen_and_e2e_command_bindings_survive() -> None:
    # The old command registrations are internal bindings, not user entry
    # points. Frozen provenance proofs drive /memory and /consolidate through a
    # real `pi --print` argv; offline E2E drives /harness through its command
    # handler. Removing any of them breaks those gates. Lock the boundary: the
    # registrations stay, but no documentation table offers them to a user.
    inject = _inject_source()
    assert 'pi.registerCommand("memory"' in inject
    assert 'pi.registerCommand("consolidate"' in inject
    guardrails = (PKG_DIR / "extensions" / "guardrails.ts").read_text(encoding="utf-8")
    assert 'pi.registerCommand("harness"' in guardrails
    readme = (PKG_DIR / "README.md").read_text(encoding="utf-8")
    # Only the command rows themselves; the prose after the table documents
    # the internal frozen bindings on purpose and is not part of the table.
    rows = [
        line
        for line in readme.split("| Command | Purpose |", 1)[1].split("## ", 1)[0].splitlines()
        if line.strip().startswith("|")
    ]
    table = "\n".join(rows)
    assert "/learning" in table
    assert "/memory" not in table and "/consolidate" not in table
    assert "/harness" not in table


def test_worker_loadout_symbols_are_retired() -> None:
    value = run_bun(r'''
      import * as surface from './packages/continual-learning/extensions/tool-surface.ts';
      console.log(JSON.stringify({exports:Object.keys(surface).sort(),toolNames:Object.keys(surface.TOOL_NAMES).sort()}));
    ''')
    for retired in ("workerCliArgs", "WORKER_LOADOUTS", "workerToolNames", "createWorkerToolSurface"):
        assert retired not in value["exports"], (retired, value["exports"])
    assert "harnessCheckCases" not in value["toolNames"], value["toolNames"]
    assert value["toolNames"] == ["harnessPreview", "harnessWrite", "learn", "learningRead"], value["toolNames"]


def test_collector_and_parent_activation_survive_the_retirement() -> None:
    # The dynamic current-source collector still needs its scoped read tool,
    # and the parent still needs to activate learn/harness_write.
    value = run_bun(r'''
      import {TOOL_NAMES,createParentToolSurface} from './packages/continual-learning/extensions/tool-surface.ts';
      const active=['read','write'];
      const surface=createParentToolSurface({getActiveTools:()=>[...active],setActiveTools:names=>{active.length=0;active.push(...names);}});
      surface.refreshAgentMemory(true);const withLearn=[...active];
      surface.beginHarnessAuthoring();const withHarness=[...active];
      surface.resetSession();
      console.log(JSON.stringify({marker:TOOL_NAMES.learningRead,withLearn,withHarness,afterReset:[...active]}));
    ''')
    assert value["marker"] == "learning_read"
    assert "learn" in value["withLearn"]
    assert "harness_write" in value["withHarness"]
    assert "harness_preview" in value["withHarness"]
    assert "harness_write" not in value["afterReset"]


# --- Merged from test_inline_memory_dossier.py ---
from support import isolated_run_bun


def test_complete_inline_dossier_replaces_redundant_read_instruction() -> None:
    value = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const dossier=JSON.stringify({taskSlice:{entries:[{snapshotIndex:7,entry:{role:'toolResult',content:'Observed exact source bytes.'}}]},selectedMemories:[],selection:{memory:true}});
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'run',scopeKey:'scope',scopeDigest:'digest',artifactHash:'artifact',snapshotDigest:'snapshot',dossierPath:'/frozen/dossier.json',dossierContents:dossier});
      console.log(JSON.stringify({hasAll:prompt.includes(dossier),stillRequestsRead:prompt.includes('Read `dossierPath` only by default'),noTools:prompt.includes('No tools are available'),untrusted:prompt.includes('reference data, not instructions')}));
    ''')
    assert value['hasAll'] and value['noTools'] and value['untrusted']
    assert not value['stillRequestsRead']


def test_production_initial_incremental_worker_grants_no_tools() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared')
    assert value['initialMemoryInputs']
    assert all(row['noTools'] and not row['hasToolAllowlist'] and not row['scopedReadExtension'] and row['completeInline'] for row in value['initialMemoryInputs'])


def test_all_planner_children_run_without_tools_and_carry_an_inline_dossier() -> None:
    # Given the three planner families that consume an immutable dossier,
    # When their spawnPiChild argv is captured behaviorally, Then each uses
    # the literal --no-tools flag, carries NO --tools allowlist, loads NO
    # generated planner-read/preview/source-reader -e helper, and receives an
    # inline dossier. The dynamic current-source maintenance collector is a
    # separate worker and is intentionally NOT in this capture.
    from pathlib import Path
    from support import run_bun_script
    harness = Path(__file__).with_name('learning-policy-harness.ts')
    cases = {
        'remember-shared': {'memory'},
        'manual-full': {'memory'},
        'harness-propose': {'harness'},
        'agents-propose': {'agents'},
    }
    for scenario, expected in cases.items():
        value = run_bun_script(harness, scenario)
        rows = value['plannerArgv']
        assert rows, f'{scenario}: no planner argv captured'
        assert {row['kind'] for row in rows} == expected, (scenario, rows)
        for row in rows:
            assert row['noTools'] and not row['hasToolAllowlist'], (scenario, row)
            assert row['generatedHelpers'] == [], (scenario, row)
            assert row['inlineDossier'], (scenario, row)
            assert row['systemPrompt'], (scenario, row)


def test_full_mode_memory_planner_grants_no_tools_with_inline_dossier() -> None:
    # Given a manual full-mode run that spawns TWO real full-mode Memory
    # planners, When their spawn argv is captured, Then each runs with no
    # tools and receives the complete immutable dossier inline, with no
    # generated planner-read extension. Before Phase 3 both spawn with
    # --tools learning_read + planner-read-*.mjs and no inline dossier.
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'manual-full')
    assert [phase for phase in value['planners'] if phase == 'memory'] == ['memory', 'memory'], value['planners']
    assert value['initialMemoryInputs']
    assert all(
        row['noTools'] and not row['hasToolAllowlist'] and not row['scopedReadExtension'] and row['completeInline']
        for row in value['initialMemoryInputs']
    ), value['initialMemoryInputs']


def test_native_pi_receives_complete_large_indexed_dossier_without_tools(tmp_path) -> None:
    import json
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {spawnSync} from 'node:child_process';
      import {locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const root=ROOT;const original={kind:'incremental-learning-dossier',taskSlice:{entries:[{role:'toolResult',content:'Exact observed source 字节\n'+('full evidence\n'.repeat(18000))}]},selectedMemories:[{name:'prior.md',content:'Complete predecessor bytes.'}]};
      const projected=JSON.stringify(locatedMemoryEvidence(original));const expected=path.join(root,'expected.txt');fs.writeFileSync(expected,projected);
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',dossierPath:'/frozen/dossier.json',dossierContents:projected});const file=path.join(root,'task.md');fs.writeFileSync(file,prompt);
      const out=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-inline-live-fixture.ts'),'--provider','inline-memory-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','@'+file],{cwd:root,env:{PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1',CL_INLINE_EXPECTED:expected},encoding:'utf8',timeout:40000,maxBuffer:16*1024*1024});
      fs.writeFileSync(path.join(root,'native-output.jsonl'),out.stdout??'');if(out.status!==0)throw Error(String(out.error??out.stderr));
      console.log(JSON.stringify({status:out.status,indexed:projected.includes('snapshotIndex')&&projected.includes('citationLines'),bytes:Buffer.byteLength(projected),received:out.stdout.includes('Complete frozen input received')}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert value['status'] == 0 and value['received'] and value['indexed'] and value['bytes'] > 128000


def test_streaming_cost_ledger_is_durable_and_bad_json_keeps_cost_unknown() -> None:
    from pathlib import Path
    from support import run_bun_script
    for mode in ('complete', 'malformed'):
        value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_MEMORY_COST_TRACE': mode})
        ledger = value['numericUsageLedgers'][0]
        assert ledger['mode'] == 0o600 and ledger['knownUsage']['cost'] == .02
        assert ledger['complete'] is (mode == 'complete')
        attempt = next(a for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory')
        if mode == 'complete':
            assert attempt['usage']['cost'] == .02 and attempt['usageLedgerId'] == ledger['ledgerId']
        else:
            assert 'usage' not in attempt and not value['registryReceipt']['usageAvailable']


# --- Merged from test_memory_body_consistency.py ---
from hashlib import sha256

from support import isolated_run_bun


def test_real_applied_body_requires_independent_consistency_and_complete_review() -> None:
    rows = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge,jevRepairFailureHints} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-body-contradiction.json','utf8'));
      const rows=[];
      for(const mode of ['contradictory','unclear','compatible','missing']){
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
          const r=JSON.parse(String(init.body));requests.push(r);const answers={};
          for(const [key,q] of Object.entries(r.questions)){
            if(mode==='missing'&&key==='coherence_0')continue;
            const keys=Object.keys(q.criteria);const label=key==='coherence_0'?mode:keys.find(k=>['grounded','compatible','unrelated'].includes(k))??keys[0];
            answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?1:0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
        }});
        const result=await judge.validate('memory',f.snapshot,[f.candidate],[]);
        rows.push({mode,result,hints:jevRepairFailureHints(result.telemetry),questions:Object.fromEntries(requests.flatMap(r=>Object.entries(r.questions)).filter(([key])=>key==='coherence_0'))});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in rows:
        assert 'coherence_0' in row['questions']
        body = row['questions']['coherence_0']['instructions']['candidate']['content']
        assert 'nothing in this path' in body and 'adopts whatever' in body
        assert 'adopting a pending promise does not settle' in row['questions']['coherence_0']['instructions']['question']
        assert row['result']['decision'] == ('allow' if row['mode'] == 'compatible' else 'propose')
        if row['mode'] == 'contradictory':
            assert row['result']['telemetry']['candidateFailures'][0]['candidateIndex'] == 0
            assert row['result']['telemetry']['candidateFailures'][0]['reason'] == 'unsupported'
        if row['mode'] in ('contradictory', 'unclear'):
            assert row['result']['telemetry']['candidateFailures'][0]['internalConsistency']
            assert 'internal-consistency' in ' '.join(row['hints'])
        if row['mode'] == 'compatible':
            assert 'coherence_0' in row['result']['candidateReview']['candidates'][0]['passedChecks']


def test_body_coherence_repair_can_update_dependent_description_without_certifying_it() -> None:
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {semanticMemoryRepairFields,mergeSemanticMemoryRepairDelta,distillReviewedNewMemory} from './packages/continual-learning/extensions/inject-memory.ts';
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const evidence={entries:[{role:'user',content:'Established fact.'}]},existing=[];
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: Established fact.\ntype: project\n---\nConflicting body.',evidence:[{index:0,quote:'Established fact.'}]};
      const candidates=[candidate],plan={operations:[],newMemories:candidates};
      const review={version:1,purpose:'diagnostic-only',complete:true,sameBatchIndependenceReviewed:false,model:'jev-1.13.0',evidenceDigest:digest(evidence),existingDigest:digest(existing),candidatesDigest:digest(candidates),candidates:[{index:0,candidateDigest:digest(candidate),outcome:'held',passedChecks:['supported_0','supported_description_0','counter_0_0','counter_description_0_0'],heldChecks:['coherence_0']}]};
      const fields=semanticMemoryRepairFields(candidates,review);
      const replacement={...candidate,content:candidate.content.replace('description: Established fact.','description: Corrected reference.').replace('Conflicting body.','Established fact.')};
      const merged=mergeSemanticMemoryRepairDelta(plan,{operations:[],newMemories:[replacement]},['fact.md'],fields,evidence);
      const distilled=distillReviewedNewMemory(plan,candidates,review,evidence,existing,1);
      const scoped=key=>semanticMemoryRepairFields(candidates,{...review,candidates:[{...review.candidates[0],heldChecks:[key]}]});
      console.log(JSON.stringify({fields,merged,distilled,plan,sourceOnly:scoped('supported_0'),counterOnly:scoped('counter_0_0'),descriptionOnly:scoped('supported_description_0'),foreign:scoped('coherence_1')??null,malformed:scoped('coherence_description_0')??null}));
    ''')
    assert value['fields'] == {'fact.md': ['body', 'description']}
    body = value['merged']['newMemories'][0]['content']
    assert 'description: Corrected reference.' in body
    assert body.endswith('Established fact.')
    assert value['sourceOnly'] == value['counterOnly'] == {'fact.md': ['body']}
    assert value['descriptionOnly'] == {'fact.md': ['description']}
    assert value['foreign'] is None and value['malformed'] is None
    assert value['distilled']['names'] == []
    assert value['distilled']['plan'] == value['plan']


def test_actual_v79_description_correction_is_not_restored_after_body_repair() -> None:
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {semanticMemoryRepairFields,mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const f=(await Bun.file('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json').json()).correctionScopeCase;
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const candidate=f.original,candidates=[candidate],plan={operations:[],newMemories:candidates};
      const review={version:1,purpose:'diagnostic-only',complete:true,candidatesDigest:digest(candidates),candidates:[{index:0,candidateDigest:digest(candidate),outcome:'held',passedChecks:['supported_0','supported_description_0','counter_0_0','counter_description_0_0'],heldChecks:['coherence_0']}]};
      const fields=semanticMemoryRepairFields(candidates,review);
      const merged=mergeSemanticMemoryRepairDelta(plan,{operations:[],newMemories:[{...candidate,content:f.submittedContent}]},[candidate.name],fields);
      const actual=merged.newMemories[0];
      console.log(JSON.stringify({fields,exactSubmitted:actual.content===f.submittedContent,oldParentReinserted:f.parentMergedContent!==f.submittedContent,identity:actual.name===candidate.name&&actual.kind===candidate.kind&&actual.classification===candidate.classification,evidence:JSON.stringify(actual.evidence)===JSON.stringify(candidate.evidence),purpose:actual.content.includes('**Why**:')&&actual.content.includes('**How to apply**:')}));
    ''')
    assert value['oldParentReinserted']
    assert value['fields'] == {'limitfunction-type-contract.md': ['body', 'description']}
    assert value['exactSubmitted'] and value['identity'] and value['evidence'] and value['purpose']


def test_real_declaration_body_keeps_assertion_level_and_all_coherence_gates() -> None:
    rows = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json','utf8')).declarationCoherenceCase;
      const rows=[];
      // This is a controlled citation context, not the original complete task.
      const entries=Array.from({length:6},()=>({role:'toolResult',content:''}));
      for(const e of f.original.evidence){entries[e.index].role=e.role;entries[e.index].content+=e.quote+'\n';}
      for(const mode of ['compatible','contradictory','unclear','low-probability','low-confidence','missing','threshold-boundary','bounded-compatible']){
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],...(mode==='bounded-compatible'?{maxRequestBytes:64000}:{}),fetch:async(_url,init)=>{
          const r=JSON.parse(String(init.body));requests.push(r);const answers={};
          for(const [key,q] of Object.entries(r.questions)){
            if(mode==='missing'&&key==='coherence_0')continue;
            const keys=Object.keys(q.criteria);const label=key==='coherence_0'&&['contradictory','unclear'].includes(mode)?mode:keys.find(k=>['grounded','compatible','unrelated'].includes(k))??keys[0];
            const probability=key==='coherence_0'&&mode==='low-probability'?.89:key==='coherence_0'&&mode==='threshold-boundary'?.9:1;
            const confidence=key==='coherence_0'&&mode==='low-confidence'?.79:key==='coherence_0'&&mode==='threshold-boundary'?.8:1;
            const other=keys.find(k=>k!==label);
            answers[key]={type:'choice',choice:label,confidence,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?probability:k===other?1-probability:0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
        }});
        const candidate={...f.original,content:f.repairedContent};
        const result=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[]);
        const q=requests.flatMap(r=>Object.entries(r.questions)).find(([k])=>k==='coherence_0')[1];
        rows.push({mode,result,question:q,completeBody:q.instructions.candidate.content===f.repairedContent.slice(f.repairedContent.indexOf('\n---\n')+5),allKeys:requests.flatMap(r=>Object.keys(r.questions))});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in rows:
        question = row['question']['instructions']['question']
        if row['mode'] == 'bounded-compatible':
            assert sha256(question.encode()).hexdigest() == '9f139dafbb64cc339fc7800428ed8f925914ac46d94b886eebf7ba75d27fd5e1'
        else:
            assert 'quotation or declaration' in question
            assert 'does not by itself assert runtime behavior' in question
            assert 'Explicit runtime assertions still require comparison' in question
        assert 'adopting a pending promise does not settle' in question
        assert row['completeBody']
        assert 'rejectOnClear?: boolean' in row['question']['instructions']['candidate']['content']
        assert 'supported_0' in row['allKeys']
        assert 'supported_description_0' in row['allKeys']
        assert any(key.startswith('counter_') for key in row['allKeys']), (row['mode'], row['allKeys'])
        assert row['result']['decision'] == ('allow' if row['mode'] in ('compatible', 'threshold-boundary', 'bounded-compatible') else 'propose')


@__import__('pytest').mark.parametrize('mixed_mutation', [False, True])
def test_normal_coherence_uses_complete_bodies_without_external_source_state(mixed_mutation):
    # Given a complete real rejected body and its original evidence,
    # When normal review asks about internal consistency,
    # Then isolate that judgment while retaining every source/counter check.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-body-contradiction.json','utf8'));
      const candidates=[f.candidate];
      const existing=MIXED?[{name:'previous.md',classification:'safe',type:'project',description:'Earlier source.',content:'OLD_BODY_IS_COMPARISON_NOT_INTERNAL_COHERENCE_AUTHORITY'}]:[];
      if(MIXED)candidates.push({...f.candidate,name:'previous.md',kind:'rewrite'});
      const requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
        const r=JSON.parse(String(init.body));requests.push(r);
        const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const keys=Object.keys(q.criteria);
          const label=keys.find(k=>['grounded','compatible','authorized','preserved','supplement','unrelated'].includes(k))??keys[0];
          return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const result=await judge.validate('memory',f.snapshot,candidates,existing);
      console.log(JSON.stringify({result,requests,candidates,sourceEntries:f.snapshot.entries.length}));
    '''.replace('MIXED', str(mixed_mutation).lower()))
    assert result['result']['decision'] == 'allow', result['result']
    coherence = [r for r in result['requests'] if any(k.startswith('coherence_') for k in r['questions'])]
    assert coherence
    seen = set()
    for request in coherence:
        assert all(k.startswith('coherence_') for k in request['questions'])
        import json
        state = json.loads(request['state']) if isinstance(request['state'], str) else request['state']
        assert not set(state).intersection({'frozenEvidence', 'supportEvidence', 'reviewEvidence', 'existingMemories', 'sourceComparisonEvidence', 'mutationComparison', 'currentMaintenanceRequest'})
        assert 'OLD_BODY_IS_COMPARISON_NOT_INTERNAL_COHERENCE_AUTHORITY' not in json.dumps(state)
        for key, question in request['questions'].items():
            index = int(key.removeprefix('coherence_'));seen.add(index)
            candidate = question['instructions']['candidate']
            if 'contentReference' in candidate:
                ref = candidate['contentReference']
                values = [v for v in state[ref['field']] if v['candidateIndex'] == ref['candidateIndex']]
                assert len(values) == 1
                body = values[0][ref['property']]
                expected = result['candidates'][index]['content']
            else:
                import re
                body = candidate['content']
                expected = re.sub(r'^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)', '', result['candidates'][index]['content'])
            assert body == expected
    assert seen == set(range(len(result['candidates'])))
    coverage = [set() for _ in result['candidates']]
    supported = set()
    for request in result['requests']:
        import json,re
        state = json.loads(request['state']) if isinstance(request['state'], str) else request['state']
        for key in request['questions']:
            if re.fullmatch(r'supported_\d+', key):supported.add(int(key.rsplit('_', 1)[1]))
            match = re.fullmatch(r'counter_(\d+)_\d+', key)
            if match:coverage[int(match[1])].update(v['index'] for v in state['reviewEvidence']['entries'])
    assert supported == seen
    assert all(rows == set(range(result['sourceEntries'])) for rows in coverage)
    assert result['result']['telemetry']['requestCount'] == len(result['requests'])


# --- Merged from test_memory_body_review.py ---
from support import isolated_run_bun


def test_actual_body_judgments_bind_exact_complete_content_and_reject_stale_witnesses() -> None:
    value = isolated_run_bun(r'''
      import {prepareMemoryBodyTargets,bindMemoryBodyJudgments} from './packages/continual-learning/extensions/memory-body-review.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-body-review.json').json();
      const targets=prepareMemoryBodyTargets([f.original,f.corrected],[]);
      const replies=[f.originalResponse,f.correctedResponse].map((r,i)=>({id:targets[i].id,...r}));
      const bound=bindMemoryBodyJudgments(targets,{reviews:replies});
      const reject=change=>{try{bindMemoryBodyJudgments(targets,change(structuredClone({reviews:replies})));return false}catch{return true}};
      console.log(JSON.stringify({bound,complete:targets[0].content===f.original.content&&targets[1].content===f.corrected.content,
        stale:reject(r=>{r.reviews[0].bodySha256=targets[1].bodySha256;return r}),
        quote:reject(r=>{r.reviews[0].conflictingQuotes[0]+=' invented';return r}),
        duplicate:reject(r=>{r.reviews[1].id=r.reviews[0].id;return r}),
        omitted:reject(r=>{r.reviews.pop();return r}),
        verdict:reject(r=>{r.reviews[0].verdict='allow';return r}),
        emptyWitness:reject(r=>{r.reviews[0].conflictingQuotes=[];return r})}));
    ''')
    assert value['complete']
    assert value['bound'][0]['verdict'] == 'contradictory'
    assert value['bound'][1]['verdict'] == 'consistent'
    assert all(value[key] for key in ['stale', 'quote', 'duplicate', 'omitted', 'verdict', 'emptyWitness'])


def test_body_worker_is_bounded_no_tool_and_preserves_complete_usage_on_refusal() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let inputs=[];
      const usage={input:20,output:10,cacheRead:0,cacheWrite:0,totalTokens:30,cost:0.001};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{inputs.push(input);return {exitCode:0,stderr:'',text:'not JSON',usage,usageLedger:{knownUsage:usage,assistantMessages:1,complete:true}}}}));
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'Complete body.'};
      const malformed=await reviewMemoryBodies({candidates:[candidate],retained:[],model:'fixture/model'});
      const bound=await reviewMemoryBodies({candidates:[{...candidate,content:'x'.repeat(65000)}],retained:[],maxRequestBytes:64_000});
      const targets=JSON.parse(inputs[0].prompt.split('\n').at(-1)).targets;
      console.log(JSON.stringify({malformed,bound:{status:bound.status,calls:bound.calls},calls:inputs.length,tools:inputs[0].tools,minimal:inputs[0].minimal,args:inputs[0].extraArgs,complete:targets[0].content===candidate.content}));
    ''')
    assert value['malformed']['status'] == 'invalid-response'
    assert value['malformed']['usage']['cost'] == 0.001
    assert value['malformed']['usageComplete']
    assert value['bound']['status'] == 'bounds' and value['bound']['calls'] == 0
    assert value['calls'] == 1 and value['tools'] == [] and value['minimal']
    assert value['args'][:2] == ['--thinking', 'xhigh'] and value['complete']
    assert value['args'][-4:] == ['--learning-output-schema', 'memory-body-review', '--learning-body-count', '1']


def test_parent_corrects_held_body_once_and_reviews_the_exact_replacement() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'memory-apply', env={'CL_JEV_FIXTURE': 'body-correction'})
    assert value.get('bodyReviewCalls') == 2
    assert value['totalRepairs'] == 1
    assert value['registryReceipt']['operations'] == 1
    assert 'Never provide concise progress updates.' not in value['conciseMemory']
    assert 'Prefer concise progress updates.' in value['conciseMemory']
    body_attempts = [a for a in value['registryReceipt']['attempts'] if a.get('diagnostic', '').startswith('Independent Memory body review:')]
    assert [a['outcome'] for a in body_attempts] == ['proposed', 'noop']
    assert all(a['usage']['cost'] == 0.001 and a['usageComplete'] for a in body_attempts)


def test_complete_bodies_split_and_keep_each_call_cost_when_a_later_group_fails() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let requests=[];
      const usage={input:20,output:10,cacheRead:0,cacheWrite:0,totalTokens:30,cost:0.001};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const targets=JSON.parse(input.prompt.split('\n').at(-1)).targets;requests.push({bytes:Buffer.byteLength(input.prompt),targets});
        if(requests.length===2)throw Error('interrupted');
        return {exitCode:0,usage,usageLedger:{knownUsage:usage,assistantMessages:1,complete:true},text:JSON.stringify({reviews:targets.map(t=>({targetIndex:t.targetIndex,verdict:'consistent',conflictingQuotes:[]}))})};
      }}));
      const {reviewMemoryBodies,memoryBodiesAllow}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const candidates=[0,1,2].map(i=>({name:`fact-${i}.md`,content:String(i)+'x'.repeat(40000)}));
      const result=await reviewMemoryBodies({candidates,retained:[],maxRequestBytes:64_000});
      console.log(JSON.stringify({status:result.status,calls:result.calls,allowed:memoryBodiesAllow(result),costs:result.batches.map(b=>({cost:b.usage?.cost,complete:b.usageComplete})),complete:requests.every((r,i)=>r.targets.length===1&&r.targets[0].content===candidates[i].content),maxBytes:Math.max(...requests.map(r=>r.bytes))}));
    ''')
    assert value['status'] == 'unavailable' and value['calls'] == 2 and not value['allowed']
    assert value['costs'] == [{'cost': 0.001, 'complete': True}, {'complete': False}]
    assert value['complete'] and value['maxBytes'] <= 64_000


def test_parent_retains_completed_source_and_body_costs_when_evidence_persistence_fails() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'memory-apply', env={'CL_JEV_FIXTURE': 'body-artifact-failure'})
    receipt = value['registryReceipt']
    assert receipt['operations'] == 0
    source = [a for a in receipt['attempts'] if a.get('jev', {}).get('model') == 'jev-1.13.0']
    body = [a for a in receipt['attempts'] if a.get('diagnostic', '').startswith('Independent Memory body review:')]
    assert len(source) == 1 and source[0]['jev']['inputTokens'] == 10
    assert len(body) == 1 and body[0]['usage']['cost'] == 0.001


def test_parent_preserves_optional_judge_missing_key_behavior_without_claiming_body_review() -> None:
    from pathlib import Path
    from support import run_bun_script
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'memory-apply', env={'CL_JEV_FIXTURE': 'body-missing-key'})
    assert value['registryReceipt']['operations'] == 1
    assert value['bodyReviewCalls'] == 0
    assert any(a.get('jev', {}).get('reason') == 'missing-key' for a in value['registryReceipt']['attempts'])


def test_invalid_body_response_retains_private_diagnostic_without_encoded_credentials() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let raw='```json\n{"reviews":[]}\n```';
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({exitCode:0,text:raw,usageLedger:{complete:true}})}));
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const dir=fs.mkdtempSync(path.join(os.tmpdir(),'body-response-'));
      try{
        const first=await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Observed fact.'}],retained:[],outputDir:dir});
        let files=fs.readdirSync(dir).filter(n=>n.startsWith('memory-body-response-'));const file=files[0];
        const retained=file?JSON.parse(fs.readFileSync(path.join(dir,file),'utf8')):null;
        raw='{"reviews":[],"token":"'+String.raw`sk\u002d`+'abcdefghijklmnopqrstuvwx"}';
        await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Observed fact.'}],retained:[],outputDir:dir});
        files=fs.readdirSync(dir).filter(n=>n.startsWith('memory-body-response-'));const second=files.find(n=>n!==file),redacted=second?JSON.parse(fs.readFileSync(path.join(dir,second),'utf8')):null;
        console.log(JSON.stringify({status:first.status,retained,privateMode:file?(fs.statSync(path.join(dir,file)).mode&0o777):null,redacted}));
      }finally{fs.rmSync(dir,{recursive:true,force:true})}
    ''')
    assert value['status'] == 'invalid-response'
    assert value['retained']['output'] == '```json\n{"reviews":[]}\n```'
    assert value['privateMode'] == 0o600
    assert value['redacted']['sensitive'] and 'output' not in value['redacted']


def test_body_model_selects_request_local_slots_instead_of_copying_parent_digests() -> None:
    value = isolated_run_bun(r'''
      const {prepareMemoryBodyTargets,bindMemoryBodySelections}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const targets=prepareMemoryBodyTargets([{name:'a.md',content:'Complete A.'},{name:'b.md',content:'Complete B.'}],[]);
      const input={reviews:[{targetIndex:1,verdict:'consistent',conflictingQuotes:[]},{targetIndex:0,verdict:'consistent',conflictingQuotes:[]}]};
      const bound=bindMemoryBodySelections(targets,input);
      const rejects=change=>{try{bindMemoryBodySelections(targets,change(structuredClone(input)));return false}catch{return true}};
      console.log(JSON.stringify({bound:bound.map(j=>j.id),expected:targets.map(t=>t.id),duplicate:rejects(r=>{r.reviews[0].targetIndex=0;return r}),foreign:rejects(r=>{r.reviews[0].targetIndex=2;return r}),digest:rejects(r=>{r.reviews[0].bodySha256=targets[0].bodySha256;return r})}));
    ''')
    assert value['bound'] == value['expected']
    assert value['duplicate'] and value['foreign'] and value['digest']


def test_actual_corrupted_id_response_remains_rejected_and_its_semantic_failure_is_preserved() -> None:
    value = isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-body-id-transcription.json').json();
      const {bindMemoryBodyJudgments,bindMemoryBodySelections}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      let oldRejected=false,newRejected=false;
      try{bindMemoryBodyJudgments([f.target],f.response)}catch{oldRejected=true}
      try{bindMemoryBodySelections([f.target],f.response)}catch{newRejected=true}
      console.log(JSON.stringify({oldRejected,newRejected,wrongSemanticVerdictRetained:f.response.reviews[0].verdict==='consistent',digestCopiedExactly:f.response.reviews[0].bodySha256===f.target.bodySha256,idChanged:f.response.reviews[0].id!==f.target.id}));
    ''')
    assert all(value.values())


def test_normal_body_review_sends_complete_large_body_without_local_byte_cap() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let complete=false,bytes=0;
      const content='Complete body. '+'x'.repeat(90000);
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const targets=JSON.parse(input.prompt.split('\n').at(-1)).targets;complete=targets[0].content===content;bytes=Buffer.byteLength(input.prompt);
        return {exitCode:0,stderr:'',text:JSON.stringify({reviews:[{targetIndex:0,verdict:'consistent',conflictingQuotes:[]}]}),usageLedger:{complete:true}};
      }}));
      const {reviewMemoryBodies}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const review=await reviewMemoryBodies({candidates:[{name:'large.md',content}],retained:[]});
      console.log(JSON.stringify({status:review.status,calls:review.calls,complete,bytes}));
    ''')
    assert value['status'] == 'reviewed' and value['calls'] == 1
    assert value['complete'] and value['bytes'] > 64_000


# --- Merged from test_memory_delete_reconsideration.py ---
from support import isolated_run_bun


def test_unvalidated_deletion_can_be_reconsidered_as_cited_rewrite_only_in_structural_slot() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let response,prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(response)}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const source='The wrapper retains clearQueue and now exposes onIdle.';
      const old={name:'contract.md',classification:'safe',content:'---\nname: contract\ndescription: Queue contract\ntype: project\n---\nThe wrapper retains clearQueue.',description:'Queue contract',type:'project'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:old.name,kind:'delete',classification:'safe',verdict:'SUPERSEDED',preservedIn:['missing.md'],evidence:[{index:1,quote:source}]}],newMemories:[]};
      const rewrite={name:old.name,kind:'rewrite',classification:'safe',content:'---\nname: contract\ndescription: Queue contract\ntype: project\n---\n'+source,evidence:[{index:0,quote:source}]};
      const input={identity,rejectedPlan:original,errors:['ineligible-source'],selectedNames:[old.name],structuralCorrection:true,allowDeleteReconsideration:true,semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:source},{role:'assistant',content:source}]},existingMemories:[old]}};
      const run=async(overrides={},operation=rewrite)=>{response={...original,operations:[operation]};return repairIncrementalMemoryPlan({...input,...overrides})};
      const good=await run();const framing=prompt;
      const held=[];
      held.push(await run({structuralCorrection:false}));
      held.push(await run({allowDeleteReconsideration:false}));
      held.push(await run({semanticContext:undefined}));
      held.push(await run({semanticContext:{...input.semanticContext,existingMemories:[]}}));
      held.push(await run({}, {...rewrite,classification:'private'}));
      held.push(await run({}, {...rewrite,content:''}));
      held.push(await run({}, {...rewrite,verdict:'SUPERSEDED'}));
      held.push(await run({}, {...rewrite,preservedIn:[]}));
      held.push(await run({}, {...rewrite,name:'other.md'}));
      held.push(await run({}, {...rewrite,evidence:[{index:1,lines:{block:0,start:1,end:1}}]}));
      held.push(await run({rejectedPlan:{...original,operations:[rewrite]}},original.operations[0]));
      console.log(JSON.stringify({good,held:held.map(x=>x.outcome),framing}));
    ''')
    assert value['good']['outcome'] == 'repaired'
    assert value['good']['plan']['operations'][0]['kind'] == 'rewrite'
    assert 'unvalidated deletion' in value['framing']
    assert all(outcome == 'failed' for outcome in value['held'])


def test_reconsideration_requires_complete_current_semantic_preservation_review() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {deletionReconsiderationReviewed} from './packages/continual-learning/extensions/inject-memory.ts';
      const evidence={contextEnabled:true,entries:[{role:'toolResult',content:'The wrapper now also exposes onIdle; retain clearQueue.'}]};
      const existing=[{name:'contract.md',classification:'safe',description:'contract',type:'project',content:'The wrapper retains clearQueue.'}];
      const candidates=[{name:'contract.md',kind:'rewrite',classification:'safe',content:'The wrapper exposes onIdle.',evidence:[{index:0,quote:evidence.entries[0].content}]}];
      let hold=false,sawPredecessor=false;const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);if(Object.keys(r.questions).some(k=>k.startsWith('counter_')))sawPredecessor ||=r.state.existingMemories.some(x=>x.name==='contract.md'&&x.content===existing[0].content);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const choice=key.startsWith('counter_')?(hold?'contradicts':'compatible'):key.startsWith('coherence_')?'compatible':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}]}))}));
      }});
      const good=await judge.validate('memory',evidence,candidates,existing);
      const check=(v=good,e=evidence,c=candidates,x=existing)=>deletionReconsiderationReviewed(['contract.md'],e,c,x,v);
      const accepted=check();const rejected=[check({...good,telemetry:{...good.telemetry,status:'disabled'}}),check({...good,candidateReview:undefined}),check(good,{...evidence,entries:[]}),check(good,[{...candidates[0],content:'changed'}]),check(good,[]),check({...good,telemetry:{...good.telemetry,completedWindows:0}}),check({...good,candidateReview:{...good.candidateReview,candidates:good.candidateReview.candidates.map(x=>({...x,passedChecks:x.passedChecks.filter(k=>!k.startsWith('counter_'))}))}})];
      rejected.push(check({...good,candidateReview:{...good.candidateReview,candidates:good.candidateReview.candidates.map(x=>({...x,passedChecks:x.passedChecks.filter(k=>!k.startsWith('counter_preservation_'))}))}}));
      rejected.push(check({...good,candidateReview:{...good.candidateReview,candidates:good.candidateReview.candidates.map(x=>({...x,passedChecks:x.passedChecks.filter(k=>!k.startsWith('counter_permission_'))}))}}));
      hold=true;const bad=await judge.validate('memory',evidence,candidates,existing);rejected.push(check(bad));
      console.log(JSON.stringify({accepted,rejected,sawPredecessor,enabled:judge.memoryReviewEnabled,disabled:createJevJudge({enabled:false}).memoryReviewEnabled,scopeOff:createJevJudge({enabled:true,scopes:['selection']}).memoryReviewEnabled}));
    ''')
    assert value['accepted'] and value['sawPredecessor']
    assert not any(value['rejected'])
    assert value['enabled'] and not value['disabled'] and not value['scopeOff']


def test_reconsideration_parent_pipeline_requires_proof_before_history_or_file_writes() -> None:
    from pathlib import Path
    from support import run_bun_script
    for mode in ('valid', 'missing-proof', 'partial-proof', 'wrong-predecessor', 'wrong-evidence', 'scope-off', 'disabled'):
        value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared',
                               env={'CL_JEV_FIXTURE': 'delete-reconsideration-' + mode})
        assert value['totalRepairs'] == 1, value
        if mode not in ('scope-off', 'disabled'):
            assert value['reviewWireCalls'] > 0, value
        if mode == 'valid':
            assert value['registryReceipt']['operations'] > 0, value
            assert value['newAppliedHistoryRecords'] > 0 and not value['memoryFilesRestored'], value
        else:
            assert value['registryReceipt']['operations'] == 0, value
            assert value['newAppliedHistoryRecords'] == 0 and value['memoryFilesRestored'], value


# --- Merged from test_memory_deletion_guard.py ---
from support import run_bun


def test_builtin_blocks_bulk_memory_deletion_but_allows_unrelated_cleanup() -> None:
    source = """
      import { DEFAULT_RULES, evaluateBash, mergeLayers } from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config = mergeLayers([{ source: 'defaults', rules: DEFAULT_RULES }]);
      const decide = command => evaluateBash(config, command);
      console.log(JSON.stringify({
        directory: decide('rm -rf .memory'),
        glob: decide('git rm .memory/*.md'),
        find: decide('find .memory -type f -delete'),
        unlink: decide('unlink .memory/MEMORY.md'),
        script: decide(`python -c "import shutil; shutil.rmtree('.memory')"`),
        privateRoot: decide('rm -rf ~/.pi/agent/memory/project-scope'),
        unrelated: decide('rm -rf dist').decision === 'execute',
      }));
    """
    payload = run_bun(source)
    for key in ['directory', 'glob', 'find', 'unlink', 'script', 'privateRoot']:
        assert payload[key]['decision'] == 'block'
    assert payload["unrelated"] is True


# --- Merged from test_memory_description_coherence.py ---
from support import isolated_run_bun


def test_actual_mislearned_description_enters_independent_complete_record_review() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json').json();
      const kit=await import('./packages/kit/src/index.ts');let request;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        request=input;return {exitCode:0,text:JSON.stringify({reviews:{'0':{verdict:'contradictory',conflictingQuotes:[
          "wrapper returns Promise & Pick<LimitFunction,'clearQueue'>",
          'The returned callable produces `Promise<ReturnType>`.']}}}),usageLedger:{complete:true}};
      }}));
      const {reviewMemoryBodies,memoryBodiesAllow,memoryBodyRepairFields}=await import('./packages/continual-learning/extensions/memory-body-review.ts');
      const review=await reviewMemoryBodies({candidates:[{name:f.filename,content:f.content}],retained:[]});
      const target=JSON.parse(request.prompt.split('\n').at(-1)).targets[0];
      console.log(JSON.stringify({review,target,allowed:memoryBodiesAllow(review),fields:memoryBodyRepairFields(review),tools:request.tools,full:target.content===f.content}));
    ''')
    assert value['full'] and value['tools'] == []
    assert value['target']['independentlyRetrievedDescription'].endswith("wrapper returns Promise & Pick<LimitFunction,'clearQueue'>")
    assert value['review']['judgments'][0]['verdict'] == 'contradictory'
    assert not value['allowed']
    # A contradiction touches the description; body-only repair must not lock it.
    assert value['fields'] == {'limit-function-type-contract.md': ['body', 'description']}
    assert all(span['text'] in value['target']['content'] for span in value['review']['judgments'][0]['witnesses'])


def test_whole_record_hold_cannot_certify_unquoted_description_as_passed() -> None:
    value = isolated_run_bun(r'''
      import {prepareMemoryBodyTargets,bindMemoryBodySelections,memoryBodyRepairFields} from './packages/continual-learning/extensions/memory-body-review.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json').json();
      const targets=prepareMemoryBodyTargets([{name:f.filename,content:f.content}],[]);
      // Actual retained worker selected these two body spans while its explanation
      // identified a description conflict. No parent authority comes from prose.
      const judgments=bindMemoryBodySelections(targets,{reviews:{'0':{verdict:'contradictory',conflictingQuotes:[
        ": ((...arguments_: Arguments) => Promise<ReturnType>) & Pick<LimitFunction, 'clearQueue'>;",
        '- The returned callable produces `Promise<ReturnType>`.']}}});
      const fields=memoryBodyRepairFields({status:'reviewed',targets,judgments,calls:1,durationMs:1,usageComplete:true});
      console.log(JSON.stringify({fields,exact:judgments[0].witnesses.every(w=>f.content.slice(w.start,w.end)===w.text)}));
    ''')
    assert value['exact']
    assert value['fields'] == {'limit-function-type-contract.md': ['body', 'description']}


# --- Merged from test_memory_failure_generalization.py ---
from pathlib import Path
import subprocess


def test_internal_runtime_properties_do_not_require_a_public_type_surface(tmp_path: Path) -> None:
    # Counterexample to the actual failed proposal's universal description.
    # A public member check says nothing about exposing incidental properties.
    source = tmp_path / 'public-contract.ts'
    source.write_text('''type PublicContract = (() => number) & { visible: boolean };
export function create(): PublicContract {
  return Object.assign(() => 1, { visible: true, internalDiagnostic: () => 'private detail' });
}
declare function expectType<T>(value: T): void;
expectType<number>(create()());
expectType<boolean>(create().visible);
''')
    result = subprocess.run(
        ['bun', 'x', 'tsc', '--noEmit', '--strict', '--skipLibCheck', '--target', 'ES2022',
         '--module', 'NodeNext', '--moduleResolution', 'NodeNext', str(source)],
        capture_output=True, text=True, timeout=40, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- Merged from test_memory_generation_whitespace.py ---
import pytest
from support import isolated_run_bun


def test_real_selected_rewrite_recovers_only_json_string_whitespace() -> None:
    # Given a real strict-schema rewrite containing raw JSON string controls,
    # When initial generation is parsed, Then all original mutation intent and
    # exact string values survive, without granting semantic acceptance.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import crypto from 'node:crypto';
      import {parseMemoryGenerationResponse} from './packages/continual-learning/extensions/inject-memory.ts';
      import {normalizeJsonStringWhitespace} from './packages/continual-learning/extensions/json-string-whitespace.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8'));
      const original=fixture.content;
      const normalized=normalizeJsonStringWhitespace(original,512000);
      const recovered=parseMemoryGenerationResponse(original);
      const expected=JSON.parse(normalized.text);
      const negatives=[original+'\n{}',original.slice(0,-1),original.replace('name:', 'name:\u0001'),original.replace('name:', 'name:\\q'), 'prefix '+original];
      console.log(JSON.stringify({digest:crypto.createHash('sha256').update(original).digest('hex')===fixture.provenance.contentSha256,
        exact:JSON.stringify(recovered.plan)===JSON.stringify(expected),counts:recovered.normalization.counts,
        unchanged:original===fixture.content,kind:recovered.plan.operations[0].kind,
        negatives:negatives.map(text=>parseMemoryGenerationResponse(text).plan===undefined),
        normal:parseMemoryGenerationResponse(JSON.stringify(expected)).normalization===undefined}));
    ''')
    assert result['digest'] and result['exact'] and result['unchanged']
    assert result['kind'] == 'rewrite'
    assert result['counts']['newline'] > 0 and result['counts']['tab'] > 0
    assert all(result['negatives']) and result['normal']


@pytest.mark.parametrize("native_retry", [False, True])
def test_actual_pi_generation_delivers_frozen_response_to_parent_parser(tmp_path, native_retry) -> None:
    import json
    result = isolated_run_bun(r'''
      import {spawnSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
      import {parsePiWorkerOutput} from './packages/kit/src/index.ts';
      import {recoverMemoryGenerationFromChild} from './packages/continual-learning/extensions/inject-memory.ts';
      import {validatePlanIdentity} from './packages/continual-learning/extensions/consolidation-run.ts';
      const root=ROOT;const nativeRetry=NATIVE_RETRY;
      fs.mkdirSync(path.join(root,'agent'),{recursive:true});
      fs.writeFileSync(path.join(root,'agent/settings.json'),JSON.stringify({retry:{enabled:true,maxRetries:1,baseDelayMs:1}}));
      const native=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
        '--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools',
        '-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
        '--generation-json-whitespace','enabled',...(nativeRetry?['--generation-native-retry','enabled']:[]),'--provider','amendment-fixture','--model','fixed','--thinking','off',
        '--no-session','--print','--mode','json','frozen generation serialization'],
        {cwd:root,env:{PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'},encoding:'utf8',timeout:40000});
      fs.writeFileSync(path.join(root,'native-generation-output.jsonl'),native.stdout);
      if(native.status!==0)throw Error(native.stderr+'\n'+native.stdout);
      const text=parsePiWorkerOutput(native.stdout).text;
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8'));
      const {plan,normalization}=recoverMemoryGenerationFromChild(native.stdout);
      const identity=Object.fromEntries(['runId','scopeDigest','snapshotDigest'].map(k=>[k,plan[k]]));
      console.log(JSON.stringify({retryClosed:native.stdout.includes('auto_retry_end'),exact:text===fixture.content,counts:normalization.counts,
        valid:validatePlanIdentity(plan,identity),foreign:validatePlanIdentity({...plan,runId:'foreign'},identity),
        wroteMemory:fs.existsSync(path.join(root,'.memory')),kind:plan.operations[0].kind}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE_RETRY', str(native_retry).lower()))
    assert result['retryClosed'] == native_retry
    assert result['exact'] and result['counts']['newline'] > 0
    assert result['kind'] == 'rewrite'
    assert result['valid'] == [] and result['foreign'] == ['plan run id mismatch']
    assert not result['wroteMemory']


def test_complete_transport_recovery_preserves_drafts_limits_and_failure() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {recoverMemoryGenerationFromChild} from './packages/continual-learning/extensions/inject-memory.ts';
      import {normalizeJsonStringWhitespace} from './packages/continual-learning/extensions/json-string-whitespace.ts';
      const raw=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8')).content;
      const plan=JSON.parse(normalizeJsonStringWhitespace(raw,512000).text);
      const frame=(text,stopReason='stop')=>JSON.stringify({type:'message_end',message:{role:'assistant',stopReason,content:[{type:'text',text}]}});
      const line=frame(raw),valid=frame(JSON.stringify(plan));
      const thought={type:'thinking',thinking:'untrusted analysis',thinkingSignature:'reasoning_content'};
      const withThinking=JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[thought,{type:'text',text:raw}]}});
      const identity={runId:plan.runId,scopeDigest:plan.scopeDigest,artifactHash:plan.artifactHash};
      const recover=(stdout,opts={})=>recoverMemoryGenerationFromChild(stdout,{expectedIdentity:identity,...opts});
      const negatives=[recover(valid+'\n'+valid),recover(line+'\n'+line),recover(line+'\n'+valid),
        recover(frame(raw,'error')),recover(frame(raw,'aborted')),recover(frame(raw,'length')),
        recover(line+'\n'+frame(raw,'error')),recover(line.slice(0,-1)),recover(frame(raw.slice(0,-1))),
        recover(line,{maxOutputBytes:10}),recover(line,{maxLineBytes:10}),recover(line+'\n{}',{maxLines:1}),
        recover(line,{maxPlanBytes:10}),recover(line,{expectedIdentity:{...identity,runId:'foreign'}}),
        recover(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'toolCall',id:'x',name:'read',arguments:{}},{type:'text',text:raw}]}})),
        recover(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'thinking',thinking:42},{type:'text',text:raw}]}}))];
      console.log(JSON.stringify({thinking:JSON.stringify(recover(withThinking).plan)===JSON.stringify(plan),positive:JSON.stringify(recover(line).plan)===JSON.stringify(plan),
        rejects:negatives.map(value=>value.plan===undefined)}));
    ''')
    assert result['thinking'] and result['positive'] and all(result['rejects'])


def test_successful_native_retry_keeps_failed_responses_and_all_parent_bounds() -> None:
    # Given the real worker lifecycle errors followed by an explicit successful
    # native retry, When its final JSON has raw string controls, Then recovery
    # matches ordinary valid-JSON extraction without adding any retry or cost.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {recoverMemoryGenerationFromChild} from './packages/continual-learning/extensions/inject-memory.ts';
      const raw=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-generation-raw-whitespace.json','utf8')).content;
      const message=(stopReason,text)=>JSON.stringify({type:'message_end',message:{role:'assistant',stopReason,content:[{type:'thinking',thinking:'untrusted analysis'},{type:'text',text}]}});
      const error=message('error','incomplete discarded provider output');
      const start=JSON.stringify({type:'auto_retry_start',attempt:1});
      const end=JSON.stringify({type:'auto_retry_end',success:true});
      const done=message('stop',raw),full=[error,start,error,start,done,end].join('\n');
      const original=full;
      const negative=[[error,done,end],[error,start,done],[error,start,done,JSON.stringify({type:'auto_retry_end',success:false})],
        [message('aborted','cancelled'),start,done,end],[done,error,start,done,end]];
      const recovered=recoverMemoryGenerationFromChild(full);
      console.log(JSON.stringify({positive:recovered.plan?.kind==='incremental-memory-plan',unchanged:full===original,
        counts:recovered.normalization?.counts,rejects:negative.map(rows=>!recoverMemoryGenerationFromChild(rows.join('\n')).plan),
        limit:!recoverMemoryGenerationFromChild(full,{maxOutputBytes:10}).plan}));
    ''')
    assert result['positive'] and result['unchanged'] and result['limit']
    assert result['counts']['newline'] > 0 and all(result['rejects'])


def test_generation_archive_suppresses_encoded_secrets_in_all_worker_messages() -> None:
    result = isolated_run_bun(r'''
      import {generationOutputContainsSensitiveMaterial} from './packages/continual-learning/extensions/inject-memory.ts';
      const fake='api_key=sk-'+'x'.repeat(40);
      const encoded=[...fake].map(c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')).join('');
      const broken='{"note":"line\nraw","value":"'+encoded+'"}';
      const frame=(text,type='text')=>JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'error',content:[type==='text'?{type,text}:{type,thinking:text}]}});
      const values=[frame(broken),frame(broken,'thinking'),frame(JSON.stringify({nested:broken})),frame('benign')+'\n'+frame(broken)];
      console.log(JSON.stringify({rejected:values.map(text=>generationOutputContainsSensitiveMaterial(text,{})),
        normalized: generationOutputContainsSensitiveMaterial(frame('benign'),{value:fake}),
        benign:generationOutputContainsSensitiveMaterial(frame('ordinary observation'),{kind:'incremental-memory-plan'})}));
    ''')
    assert all(result['rejected']) and result['normalized']
    assert not result['benign']


# --- Merged from test_memory_maintenance_audit.py ---
from support import isolated_run_bun
import pytest


def test_maintenance_audit_requires_actual_current_source_and_retains_cost_on_failure() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {mock} from 'bun:test';
      const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'memory-audit-')));const cwd=path.join(root,'project');await fs.mkdir(cwd);await fs.writeFile(path.join(cwd,'runtime.ts'),'export const runtime = "current";\n');
      const memory=path.join(root,'runtime.md');await fs.writeFile(memory,'Old runtime knowledge.');let mode='good';
      const kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async options=>{
        const scope=JSON.parse(options.prompt.split('\n').at(-1));
        if(JSON.stringify(options.tools)!==JSON.stringify(['learning_read']) || !options.minimal)throw Error('Audit must not grant native tools');
        const {recordMaintenanceRead}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
        if(mode!=='good')await recordMaintenanceRead(scope.observationsPath, {path:memory,offset:1,limit:200,result:'Old runtime knowledge.\n[lines 1-1 of 1]'});
        const {readPlannerFileSnapshot}=await import('./packages/continual-learning/extensions/planner-read-scope.ts');
        if(mode==='good'){const source=await readPlannerFileSnapshot('runtime.ts',scope.readScope);await recordMaintenanceRead(scope.observationsPath,{path:path.join(cwd,'runtime.ts'),offset:1,limit:200,result:source.text,sha256:source.sha256});}
        if(mode==='failed')return {exitCode:1,stderr:'untrusted worker error',text:'',usage:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:0.01}};
        return {exitCode:0,stderr:'',text:'The runtime is current.',usage:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:0.01}};
      }}));
      const {auditMemoryMaintenanceSources,isMemoryMaintenanceRequest}=await import('./packages/continual-learning/extensions/memory-maintenance-audit.ts');
      const input={cwd,request:'整理记忆',memoryFiles:[memory],outputDir:root};
      const good=await auditMemoryMaintenanceSources(input);await good.assertSourcesUnchanged();
      await fs.writeFile(path.join(cwd,'runtime.ts'),'export const runtime = "changed";\n');let stale=false;try{await good.assertSourcesUnchanged()}catch{stale=true}
      mode='empty';const empty=await auditMemoryMaintenanceSources(input);mode='failed';const failed=await auditMemoryMaintenanceSources(input);
      console.log(JSON.stringify({good:{outcome:good.outcome,entries:good.entries,usage:good.usage},empty:{outcome:empty.outcome,usage:empty.usage},failed:{outcome:failed.outcome,usage:failed.usage},stale,maintenance:['整理记忆','帮我整理记忆','organize memories','Remember I prefer pnpm.'].map(isMemoryMaintenanceRequest)}));
      await fs.rm(root,{recursive:true,force:true});
    ''')
    assert result['good']['outcome'] == 'observed'
    assert len(result['good']['entries']) == 2
    assert result['good']['entries'][1]['message']['role'] == 'toolResult'
    assert 'export const runtime' in result['good']['entries'][1]['message']['content'][0]['text']
    assert 'Old runtime knowledge' not in str(result['good']['entries'])
    assert result['stale'] is True
    assert result['maintenance'] == [True, True, True, False]
    for key in ('empty', 'failed'):
        assert result[key]['outcome'] == 'failed'
        assert result[key]['usage']['cost'] == 0.01


def test_scoped_source_reads_bind_full_revision_and_block_nested_memory_and_dependencies() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {readPlannerFileSnapshot,registerPlannerRead} from './packages/continual-learning/extensions/planner-read-scope.ts';
      const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'audit-boundary-')));
      await fs.writeFile(path.join(root,'source.ts'),'visible\noriginal tail\n');
      const scope={cwd:root,files:[],roots:[root],excludedComponents:['.memory','.pi','node_modules']};
      const first=await readPlannerFileSnapshot('source.ts',scope,1,1);await fs.writeFile(path.join(root,'source.ts'),'visible\nchanged tail\n');const second=await readPlannerFileSnapshot('source.ts',scope,1,1);
      const blocked=[];
      for(const dir of ['nested/.memory','nested/.pi','nested/node_modules']){await fs.mkdir(path.join(root,dir),{recursive:true});const file=path.join(root,dir,'record.md');await fs.writeFile(file,'Existing note, not source.');try{await readPlannerFileSnapshot(file,scope);blocked.push(false)}catch{blocked.push(true)}}
      let definition;const loadouts=[],observations=[];
      registerPlannerRead({registerTool:t=>definition=t,on:()=>{},setActiveTools:t=>loadouts.push(t)},scope,async read=>{observations.push(read)},2);
      const all=await Promise.allSettled(Array.from({length:3},()=>definition.execute('read',{path:'source.ts'},new AbortController().signal)));
      console.log(JSON.stringify({sameVisible:first.text===second.text,differentRevision:first.sha256!==second.sha256,blocked,statuses:all.map(x=>x.status),loadouts,observations:observations.map(x=>({sha256:x.sha256,error:x.error}))}));await fs.rm(root,{recursive:true,force:true});
    ''')
    assert result['sameVisible'] and result['differentRevision']
    assert all(result['blocked'])
    assert result['statuses'] == ['fulfilled', 'fulfilled', 'rejected']
    assert all(loadout == [] for loadout in result['loadouts'])
    assert sum(bool(row.get('error')) for row in result['observations']) == 1
    assert sum(bool(row.get('sha256')) for row in result['observations']) == 2


def test_source_observations_append_without_omitting_original_task_evidence() -> None:
    result = isolated_run_bun(r'''
      import {appendMemorySourceObservations,requestedMemoryTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const original=requestedMemoryTaskSlice('整理记忆',[{role:'user',content:'Do not write Memory during this source task.'},{role:'toolResult',content:'original observation'}]);
      const source={role:'toolResult',content:'current source'};const merged=appendMemorySourceObservations(original,[source]);
      const rejected=[Array.from({length:256},()=>source),[{role:'toolResult',content:'x'.repeat(512000)}]].map(entries=>{try{appendMemorySourceObservations(original,entries);return false}catch{return true}});
      console.log(JSON.stringify({merged,original,exact:merged.entries.slice(0,3).every((e,i)=>e===original.entries[i]),rejected}));
    ''')
    assert result['exact'] and len(result['merged']['entries']) == 4
    assert result['merged']['memoryRequest'] == result['original']['memoryRequest'] == {'entryIndex': 2}
    assert result['merged']['entries'][2]['message']['content'] == '整理记忆'
    assert all(result['rejected'])


@pytest.mark.parametrize('overflow', [False, True])
def test_actual_pi_source_audit_exhaustion_and_overflow(tmp_path, overflow) -> None:
    import json
    import subprocess
    from pathlib import Path
    from live_acceptance_support import isolated_environment, workspace_pi
    from support import REPO
    project, agent = tmp_path / 'project', tmp_path / 'agent'
    project.mkdir(); agent.mkdir()
    source = project / 'runtime.ts'
    source.write_text('export const runtime = "current";\n')
    session = tmp_path / 'session.jsonl'
    command = [workspace_pi(REPO), '--offline', '--no-extensions', '--no-context-files', '--no-skills',
               '--no-prompt-templates', '--no-themes', '--no-approve', '--thinking', 'off', '--tools', 'learning_read',
               '-e', str(Path(__file__).with_name('maintenance-reader-live-fixture.ts')),
               '--model', 'maintenance-reader-fixture/deterministic', '--session', str(session),
               '--print', '--mode', 'json', 'Inspect source read scope']
    environment = isolated_environment(tmp_path, agent)
    if overflow:
        environment['MAINTENANCE_READER_OVERFLOW'] = '1'
    result = subprocess.run(command, cwd=project, env=environment, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode()
    rows = [json.loads(line) for line in session.read_text().splitlines()]
    assert [row['data']['tools'] for row in rows if row.get('customType') == 'maintenance-reader-provider'] == ([['learning_read']] if overflow else [['learning_read'], []])
    observations = [row['data'] for row in rows if row.get('customType') == 'maintenance-reader-observed']
    assert len(observations) == (3 if overflow else 2)
    successes = sum(bool(row.get('sourceSha256')) for row in observations)
    errors = [row['error'] for row in observations if row.get('error')]
    if overflow:
        # Pi executes a batch concurrently. Abort may cancel admitted reads
        # still in flight; the entire overflowing audit must remain invalid.
        assert successes <= 2
        assert errors.count('Source audit read budget exceeded') == 1
        assert all(error in ('Source audit read budget exceeded', 'Scoped source read refused') for error in errors)
    else:
        assert successes == 2 and errors == []
    assert source.read_text() == 'export const runtime = "current";\n'


# --- Merged from test_memory_maintenance_focus.py ---
from pathlib import Path


PROMPT = Path(__file__).resolve().parents[1] / 'prompts/incremental-memory-consolidator.md'


def test_maintenance_prompt_requires_claim_focused_corrections_and_full_context() -> None:
    text = PROMPT.read_text()
    assert 'Organization is not wholesale summarization' in text
    assert 'Identify the particular obsolete, contradicted or misleading claim' in text
    assert 'Preserve unrelated established knowledge and its material conditions' in text
    assert 'Do not shorten or remove source conditions to reduce review cost' in text
    assert 'All original task evidence remains subject to complete review' in text


# --- Merged from test_memory_required_body.py ---
from support import isolated_run_bun


def test_real_frontmatter_only_proposal_requires_actual_knowledge_body() -> None:
    # Given the original completed real plan has only discovery metadata,
    # When parent normalizes it before body/Jev review, Then reject it as a
    # structural error without turning the description into knowledge.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-frontmatter-only.json','utf8'));
      const original=JSON.stringify(fixture.plan);
      const plan=resolveMemoryPlanCitations(fixture.plan,fixture.snapshot);
      let error;try{normalizeNewMemoryProposals(plan,fixture.snapshot)}catch(e){error=e.message}
      console.log(JSON.stringify({error,unchanged:original===JSON.stringify(fixture.plan)}));
    ''')
    assert value.get('error') and 'non-empty Memory body' in value['error']
    assert value['unchanged']


def test_generation_and_repair_schemas_require_body_after_metadata() -> None:
    value = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const delta=learningOutputSchema('memory-delta');
      const amendment=learningOutputSchema('memory-amendment');
      const fields=[delta.properties.newMemories.items.anyOf[0].properties.content,
        delta.properties.operations.items.anyOf[0].properties.content,
        amendment.properties.replacements.items.properties.content];
      const empty='---\nname: fact\ndescription: Discovery metadata\ntype: project\n---\n  \t\n';
      const complete=empty+'Actual grounded body.\n';
      console.log(JSON.stringify(fields.map(field=>({pattern:field.pattern,
        emptyAccepted:field.pattern===undefined||new RegExp(field.pattern).test(empty),
        completeAccepted:field.pattern===undefined||new RegExp(field.pattern).test(complete)}))));
    ''')
    assert all(item.get('pattern') and not item['emptyAccepted'] and item['completeAccepted'] for item in value)


def test_parent_and_independent_validator_agree_on_metadata_only_writes() -> None:
    import importlib.util
    import json
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "validate-consolidate.py"
    spec = importlib.util.spec_from_file_location("memory_body_validator", script)
    assert spec and spec.loader
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    header = "---\nname: fact\ndescription: Discovery metadata\ntype: project\n---\n"
    documents = [header, header + " \t\n", "\ufeff" + header.replace("\n", "\r\n") + "\u00a0\ufeff", "", "\t\n",
                 header + "Grounded knowledge.\n", "Legacy knowledge without frontmatter.\n"]
    results = []
    for content in documents:
        try:
            validator.require_memory_body(content, "candidate")
            results.append(True)
        except validator.ValidationError as error:
            assert "non-empty Memory body" in str(error)
            results.append(False)
    actual = isolated_run_bun(r'''
      import {assertMemoryBodyContent} from './packages/continual-learning/extensions/consolidation-run.ts';
      const documents=''' + json.dumps(documents) + r''';
      console.log(JSON.stringify(documents.map(content=>{try{assertMemoryBodyContent(content,'candidate');return true}catch{return false}})));
    ''')
    assert actual == results == [False] * 5 + [True, True]
    # The independent validator must enforce the rule on actual mutation operations.
    for kind in ("create", "rewrite"):
        try:
            validator.validate_operations([{"name": "fact.md", "kind": kind, "classification": "private", "content": header}],
                ["fact.md"], {"fact.md": {"classification": "private"}}, {"fact.md": {"verdict": "KEEP"}}, None, [])
        except validator.ValidationError as error:
            assert "non-empty Memory body" in str(error)
        else:
            raise AssertionError("Independent validator admitted a metadata-only write")


def test_actual_pi_structural_repair_has_source_and_keeps_parent_intent(tmp_path) -> None:
    import json
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');const root=ROOT;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const env={PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'};
        const native=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),'--missing-memory-body','enabled','--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json',input.prompt],{cwd:root,env,encoding:'utf8',timeout:40000});
        fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);
        if(native.status!==0)throw new Error(native.stderr+'\n'+native.stdout);
        return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {normalizeNewMemoryProposals}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const snapshot={contextEnabled:true,entries:[{type:'message',message:{role:'toolResult',content:'Correct claim'}}]};
      const candidate={name:'fact.md',kind:'project',classification:'private',content:'---\nname: fact\ndescription: Discovery only\ntype: project\n---\n',evidence:[{index:0,quote:'Correct claim'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]};
      const input={identity,rejectedPlan:original,errors:['candidate requires a non-empty Memory body'],selectedNames:[],structuralCorrection:true,semanticContext:{frozenEvidence:snapshot,existingMemories:[]}};
      const result=await repairIncrementalMemoryPlan(input);
      const normalized=result.plan?normalizeNewMemoryProposals(result.plan,snapshot):[];
      console.log(JSON.stringify({result,normalized,original,wroteMemory:fs.existsSync(path.join(root,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert value['result']['outcome'] == 'repaired', value['result']
    old = value['original']['newMemories'][0]
    corrected = value['result']['plan']['newMemories'][0]
    assert all(corrected[key] == old[key] for key in ('name', 'kind', 'classification', 'evidence'))
    assert corrected['content'] == old['content'] + 'Correct claim\n'
    assert len(value['normalized']) == 1 and not value['wroteMemory']
    # This proves the native structural correction interface, not semantic approval or task benefit.


# --- Merged from test_memory_review_consent.py ---
from pathlib import Path

from support import isolated_run_bun, run_bun_script
import pytest


@pytest.mark.parametrize('scenario', ['remember-private-maintenance', 'remember-private-request'])
def test_private_memory_needs_no_consent_gate(scenario: str) -> None:
    # All Memory is reviewable by default: no dialog, no private-memory hold,
    # and no retired `allowPrivateMemory` key written into the config.
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), scenario)
    assert value['consentCount'] == 0, value
    assert value['consentConfigUnchanged'], value
    receipt = value['registryReceipt']
    assert 'private-memory-denied' not in str(receipt), receipt
    assert not any('consent' in str(a.get('diagnostic', '')).lower() for a in receipt['attempts']), receipt


def test_preflight_receipt_has_zero_calls_and_rejects_untrusted_count() -> None:
    value = isolated_run_bun(r'''
      import {buildLearningReceipt,learningSummaryDetails,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'failed',operations:0,durationMs:0,modelCalls:0,usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:0}}]);
      const invalid=structuredClone(receipt);invalid.attempts[0].modelCalls=-1;
      console.log(JSON.stringify({text:learningSummaryDetails(receipt).join("\n"),valid:isLearningPipelineReceipt(receipt),invalid:isLearningPipelineReceipt(invalid)}));
    ''')
    assert 'calls · 0' in value['text'] and value['valid'] and not value['invalid']


# --- Merged from test_memory_task_quality.py ---
from memory_task_quality_cases import cases


def test_cases_have_independent_oracles_and_no_hidden_file_leak():
    from live_memory_task_quality import score, summarize
    rows = cases('heldout')
    assert len(rows) == 12
    assert len({row['id'] for row in rows}) == 12
    for row in rows:
        assert row['expected'] not in row['task'] or row['expected'] == 'unknown'
        assert score({'value': row['expected']}, row)['correct']
        assert not score({'value': row['obsolete']}, row)['correct']
        assert not score({'value': row['expected'], 'extra': True}, row)['correct']
    result = summarize([{'id':'a','category':'durable','baseline':{'correct':False},'memory':{'correct':True}},
                        {'id':'b','category':'conflict','baseline':{'correct':True},'memory':{'correct':False}}])
    assert result['improvements'] == ['a'] and result['regressions'] == ['b']
    assert not result['acceptance']


def test_training_errors_cannot_pass_acceptance_even_if_answers_are_correct():
    from live_memory_task_quality import summarize
    row = {'id':'a','category':'durable','training':[{'error':'process-timeout'}],
           'baseline':{'correct':False},'memory':{'correct':True}}
    result = summarize([row])
    assert not result['acceptance']
    assert result['trainingFailures'] == ['a']


def test_task_cannot_modify_current_evidence_or_leave_cross_arm_files(tmp_path):
    from live_memory_task_quality import task_snapshot, assert_task_unchanged
    import pytest
    (tmp_path/'current.json').write_text('{"value":"current"}')
    before = task_snapshot(tmp_path)
    (tmp_path/'answer.json').write_text('{"value":"answer"}')
    assert_task_unchanged(tmp_path,before)
    (tmp_path/'leak.txt').write_text('leak')
    with pytest.raises(RuntimeError,match='Task mutated'):
        assert_task_unchanged(tmp_path,before)


def test_provider_failure_is_not_a_memory_improvement():
    from live_memory_task_quality import summarize
    row = {'id':'a','category':'durable', 'baseline':{'correct':False,'errors':['rate limited']},
           'memory':{'correct':True}}
    result = summarize([row])
    assert result['improvements'] == []
    assert result['invalidPairs'] == ['a']
    assert not result['acceptance']


def test_real_result_message_receipts_and_missing_learning_are_checked():
    from live_memory_task_quality import learning_receipts, training_ok
    receipt = {'kind':'learning-pipeline-receipt','attempts':[{'phase':'memory','outcome':'rejected'}]}
    messages = [{'role':'custom','customType':'continual-learning-result','details':receipt}]
    found = learning_receipts(messages)
    assert found == [receipt]
    assert not training_ok({'training':[{'exitCode':0,'errors':[],'receipts':found}]})
    assert not training_ok({'training':[{'exitCode':0,'errors':[],'receipts':[]}]})


def test_transfer_task_requires_memory_plus_current_catalogue():
    rows = cases('heldout',task_type='resolve')
    assert len(rows) == 12
    for row in rows:
        assert 'catalog.json' in row['files']
        assert row['expected'] not in '\n'.join(row['training']) or row['expected'] == 'unknown'
        assert row['expected'] not in row['task'] or row['expected'] == 'unknown'
        if row['category'] in {'durable','conflict','correction'}:
            assert row['expected'] != row['knowledgeExpected']
            assert row['files']['catalog.json']['aliases'][row['knowledgeExpected']]['handoffValue'] == row['expected']


def test_transfer_catalogue_has_distractors_and_no_fixed_answer_position():
    rows = cases('heldout',task_type='resolve')
    positions = set()
    for row in rows:
        keys = list(row['files']['catalog.json']['aliases'])
        assert len(keys) >= 5
        positions.add(keys.index(row['currentAlias']))
    assert len(positions) >= 3


def test_case_category_is_not_revealed_in_task_subject():
    for row in cases('heldout',task_type='resolve'):
        assert row['category'] not in row['subject']


# --- Merged from test_memory_write_guard.py ---
from support import run_bun


def test_reference_memory_is_read_only_for_ordinary_model_tools():
    result = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {memoryWriteBlock} from './packages/continual-learning/extensions/memory-write-guard.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const base=await fs.mkdtemp(path.join(os.tmpdir(),'cl-write-boundary-'));
      process.env.PI_CODING_AGENT_DIR=path.join(base,'agent');
      const cwd=path.join(base,'project');await fs.mkdir(cwd);Bun.spawnSync(['git','init','-q',cwd]);
      const roots=resolveMemoryPaths(cwd);await fs.mkdir(roots.harnessDir,{recursive:true});
      await fs.mkdir(roots.publicDir,{recursive:true});await fs.symlink(roots.publicDir,path.join(cwd,'alias'));
      try {
        const check=(name,p)=>Boolean(memoryWriteBlock(cwd,name,{path:p}));
        console.log(JSON.stringify({shared:check('write','.memory/answer.json'),private:check('edit',path.join(roots.harnessDir,'fact.md')),
          alias:check('write','alias/new.md'),traversal:check('write','work/../.memory/fact.md'),
          output:check('write','answer.json'),similar:check('write','.memory-notes.md'),read:check('read','.memory/fact.md')}));
      } finally {await fs.rm(base,{recursive:true,force:true})}
    ''')
    assert result == {'shared':True,'private':True,'alias':True,'traversal':True,
                      'output':False,'similar':False,'read':False}


def test_write_guard_matches_native_pi_path_normalization():
    result = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {pathToFileURL} from 'node:url';
      import {createWriteTool} from '@earendil-works/pi-coding-agent';
      import {memoryWriteBlock} from './packages/continual-learning/extensions/memory-write-guard.ts';
      const base=await fs.mkdtemp(path.join(os.tmpdir(),'cl-path-parity-'));
      const cwd=path.join(base,'project space');await fs.mkdir(cwd);Bun.spawnSync(['git','init','-q',cwd]);
      process.env.PI_CODING_AGENT_DIR=path.join(base,'agent');
      const target=path.join(cwd,'.memory/fact.md');
      const paths=['@.memory/fact.md',pathToFileURL(target).href,'~/' + path.relative(os.homedir(),target),target.replaceAll(' ','\\u00a0')];
      try {
        const rows=[];
        for(const p of paths){
          await createWriteTool(cwd).execute('test',{path:p,content:'native'});
          rows.push({native:await fs.readFile(target,'utf8')==='native',blocked:Boolean(memoryWriteBlock(cwd,'write',{path:p}))});
          await fs.unlink(target);
        }
        console.log(JSON.stringify(rows));
      } finally {await fs.rm(base,{recursive:true,force:true})}
    ''')
    assert all(row['native'] and row['blocked'] for row in result)


# --- Merged from test_preference_demotion.py ---
"""A stated preference must not reach the project surface, whatever the planner declared.

The parent already refuses a plan that declares ``preference`` with a ``safe``
classification, so a declared contradiction cannot leak. It could not catch a
*mislabel*: the planner declaring ``project`` and ``safe`` for something the user
stated as a personal preference. The live smoke reproduced that three runs in a
row, because a guard on the declared kind is only as strong as the planner's
honesty about it.

The demotion is one-directional by construction. It can only move ``safe`` to
``private``, so a false positive costs a collaborator one lookup and never costs
the user their privacy.
"""


from support import isolated_run_bun

SNIPPET = r"""
      import { normalizeNewMemoryProposals, statesPreferenceAsSuch } from './packages/continual-learning/extensions/consolidation-run.ts';
      const entries = [
        { message: { role: 'user', content: 'I prefer concise progress updates.' } },
        { message: { role: 'user', content: 'This project ships through the canary channel first.' } },
      ];
      const proposal = (overrides) => ({
        name: 'project_probe.md', kind: 'project', content: 'A durable statement.',
        evidence: [{ index: 0, source: 'user', quote: entries[0].message.content, count: 1 }],
        ...overrides,
      });
      const normalize = (over) => {
        try {
          // `contextEnabled` is what makes a snapshot eligible to ground
          // proposals; without it the parent refuses before classification.
          const out = normalizeNewMemoryProposals({ newMemories: [proposal(over)] }, { contextEnabled: true, entries });
          return out[0].classification;
        } catch (error) { return `error: ${error.message}`; }
      };
      console.log(JSON.stringify({
        statedPreferenceDetected: [
          statesPreferenceAsSuch('I prefer concise updates.'),
          statesPreferenceAsSuch('我更喜欢简短更新。'),
          statesPreferenceAsSuch('This project ships through the canary channel first.'),
          statesPreferenceAsSuch('Run bun run check to verify.'),
        ],
        // The claim itself is checked, not only the quote it cites. A live run
        // cited an unrelated sentence and a preference was mirrored anyway.
        contentStatesIt: (() => {
          try {
            const out = normalizeNewMemoryProposals({ newMemories: [{
              ...proposal({ classification: 'safe' }),
              content: 'The user prefers concise progress updates.',
              evidence: [{ index: 1, source: 'user', quote: entries[1].message.content, count: 1 }],
            }] }, { contextEnabled: true, entries });
            return out[0].classification;
          } catch (error) { return `error: ${error.message}`; }
        })(),
        mislabelledSafe: normalize({ classification: 'safe' }),
        honestSafe: normalize({
          evidence: [{ index: 1, source: 'user', quote: entries[1].message.content, count: 1 }],
        }),
        explicitPrivate: normalize({ classification: 'private' }),
        declaredContradiction: normalize({ kind: 'preference', classification: 'safe' }),
      }));
"""


def test_a_stated_preference_is_demoted_whatever_the_planner_declared() -> None:
    value = isolated_run_bun(SNIPPET)
    detected = value["statedPreferenceDetected"]
    assert detected[0] is True, value
    assert detected[1] is True, value
    # The pattern must not fire on ordinary project or tooling statements, or
    # every safe entry would be demoted and the shared surface would go empty.
    assert detected[2] is False, value
    assert detected[3] is False, value

    # A planner that says `project` + `safe` about a stated preference is
    # demoted rather than trusted.
    assert value["mislabelledSafe"] == "private", value
    # A proposal that states the preference in its own body is demoted even when
    # it cites evidence that does not mention one.
    assert value["contentStatesIt"] == "private", value
    # A project fact resting on ordinary evidence stays shareable.
    assert value["honestSafe"] == "safe", value
    assert value["explicitPrivate"] == "private", value
    # A declared contradiction resolves like a stated preference: the knowledge
    # is kept and made private. Rejecting threw away real learning over a label
    # error and aborted the phase.
    assert value["declaredContradiction"] == "private", value


# --- Merged from test_quoted_description_distillation.py ---
import pytest
from support import isolated_run_bun


def test_quoted_description_distillation_keeps_actual_holds_and_requires_complete_description_passes():
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {distillReviewedNewMemory} from './packages/continual-learning/extensions/inject-memory.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-quoted-description-distillation.json').json();
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      if(digest(f.candidates)!==f.review.candidatesDigest||digest(f.evidence)!==f.review.evidenceDigest||digest(f.existing)!==f.review.existingDigest)throw Error('Frozen real review mismatch');
      const run=(plan=f.plan,review=f.review,evidence=f.evidence)=>distillReviewedNewMemory(plan,f.candidates,review,evidence,f.existing,f.windows);
      const actual=run();
      // Controlled checklist variation exercises the eligible path only. The
      // retained real checklist below must remain held, never called positive.
      const eligible=structuredClone(f.review);
      for(const c of eligible.candidates){
        const passed=c.heldChecks.filter(x=>x.includes('_description_'));
        c.heldChecks=c.heldChecks.filter(x=>!x.includes('_description_'));
        c.passedChecks.push(...passed);
      }
      const narrow=(plan=f.plan)=>run(plan,eligible);
      const narrowed=narrow();const changed=structuredClone(f.plan);changed.newMemories[0].content+='\nAn unreviewed claim.';
      const newSource=structuredClone(f.evidence);newSource.entries.push({role:'user',content:'A later correction.'});
      const newCitation=structuredClone(f.plan);newCitation.newMemories[0].evidence=[{index:0,quote:'unreviewed source'}];
      const stale=run(f.plan,{...f.review,candidatesDigest:'0'.repeat(64)});
      console.log(JSON.stringify({narrowed,original:f.plan,actual,changed:narrow(changed),newSource:run(f.plan,f.review,newSource),newCitation:narrow(newCitation),stale}));
    ''')
    assert value['actual']['names']==[]
    assert value['narrowed']['names']==[]
    assert value['narrowed']['plan']==value['original']
    assert value['narrowed']['plan']['operations']==value['original']['operations']
    assert 'limitfunction-onidle-contract.md' not in value['changed']['names']
    assert 'limitfunction-onidle-contract.md' not in value['newCitation']['names']
    assert value['newSource']['names']==[] and value['stale']['names']==[]



@pytest.mark.parametrize("model", ["jev-1.13.0", "jev-1.14.0"])
def test_fresh_corrected_description_is_a_candidate_until_another_complete_parent_review(model: str):
    from pathlib import Path
    from support import run_bun_script
    fixture=Path(__file__).with_name('learning-policy-harness.ts')
    passed=run_bun_script(fixture,'remember-allowed',env={'CL_JEV_FIXTURE':'distill-fresh','CL_JEV_MODEL':model})
    held=run_bun_script(fixture,'remember-allowed',env={'CL_JEV_FIXTURE':'distill-fresh-held','CL_JEV_MODEL':model})
    assert passed['semanticRepairs']==1 and passed['jevValidations']==['memory']*3
    assert passed['bodyReviewCalls']==3
    assert passed['registryReceipt']['operations']==1
    assert passed['conciseMemory'].endswith('"Prefer concise progress updates."\n')
    assert 'unsupported explanation' not in passed['conciseMemory']
    assert held['semanticRepairs']==1 and held['jevValidations']==['memory']*3
    assert held['bodyReviewCalls']==3 and held['registryReceipt']['operations']==0
    assert not held.get('conciseMemory')

    for result in (passed,held):
        jev_attempts=[a for a in result['registryReceipt']['attempts'] if a.get('jev')]
        assert all(a['jev']['model']==model for a in jev_attempts)
        assert len(jev_attempts)==3
        assert sum(a['jev']['requestCount'] for a in jev_attempts)==3
        assert sum(a['jev']['estimatedCostUsd'] for a in jev_attempts)==.003
        assert sum('before deterministic narrowing' in a.get('diagnostic','') for a in jev_attempts)==1
