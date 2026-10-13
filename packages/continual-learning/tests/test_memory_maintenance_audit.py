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
      import {appendMemorySourceObservations} from './packages/continual-learning/extensions/incremental-learning.ts';
      const original={kind:'learning-task-slice',version:1,entries:[{role:'user',content:'整理记忆'},{role:'toolResult',content:'original observation'}]};
      const source={role:'toolResult',content:'current source'};const merged=appendMemorySourceObservations(original,[source]);
      const rejected=[Array.from({length:256},()=>source),[{role:'toolResult',content:'x'.repeat(512000)}]].map(entries=>{try{appendMemorySourceObservations(original,entries);return false}catch{return true}});
      console.log(JSON.stringify({merged,original,exact:merged.entries.slice(0,2).every((e,i)=>e===original.entries[i]),rejected}));
    ''')
    assert result['exact'] and len(result['merged']['entries']) == 3
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
