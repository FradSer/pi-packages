from support import isolated_run_bun


def test_real_field_repair_preserves_parent_validated_observations() -> None:
    # Given the actual v10 rewrite, When only its held body is repaired,
    # Then original source observations survive omitted or forged metadata.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-grounding.json','utf8'));
      const original={operations:[fixture.original],newMemories:[]};
      const rows=[];
      for(const fields of [['body'],['description'],['body','description']]) {
        for(const extra of [{},{observations:[{path:'invented.ts',status:'found'}]}]) {
          const corrected={...fixture.corrected,...extra};
          const merged=mergeSemanticMemoryRepairDelta(original,{operations:[corrected],newMemories:[]},[fixture.original.name],{[fixture.original.name]:fields});
          rows.push({observations:merged.operations[0].observations,body:merged.operations[0].content});
        }
      }
      console.log(JSON.stringify({expected:fixture.original.observations,rows}));
    ''')
    assert result['expected']
    assert all(row.get('observations') == result['expected'] for row in result['rows'])


def test_unobserved_grounding_never_infers_claim_kind_from_filename() -> None:
    # Given project facts and preferences without observations, When expanded,
    # Then all are honestly unverified rather than classified by filename.
    result = isolated_run_bun(r'''
      import fs from 'node:fs/promises'; import path from 'node:path';
      import {expandIncrementalMemoryPlan} from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      const root=process.env.PI_CODING_AGENT_DIR;
      const names=['project_fact.md','limit_function_type_contract.md','preference_style.md'];
      const harness=path.join(root,'memory'),pub=path.join(root,'public');await fs.mkdir(harness);await fs.mkdir(pub);
      await fs.writeFile(path.join(harness,'MEMORY.md'),names.map(name=>`- [${name}](${name})`).join('\n'));
      for(const name of names)await fs.writeFile(path.join(harness,name),'---\ntype: project\n---\nRepository source claim.\n');
      const run={manifest:{runId:'r',scopeKey:'s',scopeDigest:'d',snapshotDigest:'h',cwd:root,harnessDir:harness,publicDir:pub,sourceHashes:{harness:{},public:{}}}};
      const plan=await expandIncrementalMemoryPlan(run,names,{kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'h',snapshotDigest:'h',operations:[],newMemories:[]});
      console.log(JSON.stringify(plan.grounding));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert {row['status'] for row in result} == {'UNVERIFIABLE'}
    assert len({row['reason'] for row in result}) == 1
    assert all('does not make a repository claim' not in row['reason'] for row in result)


def test_parent_recomputes_optional_content_hash_after_field_repair() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs'; import {createHash} from 'node:crypto';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-grounding.json','utf8'));
      const hash=text=>createHash('sha256').update(text).digest('hex');
      const prior={...fixture.original,contentSha256:hash(fixture.original.content)};
      const rows=[];
      for(const fields of [['body'],['description'],['body','description']]) {
        const corrected={...fixture.corrected,content:fixture.corrected.content.replace(/description: [^\n]+/,'description: A corrected declared contract'),contentSha256:'0'.repeat(64)};
        const result=mergeSemanticMemoryRepairDelta({operations:[prior],newMemories:[]},{operations:[corrected],newMemories:[]},[prior.name],{[prior.name]:fields}).operations[0];
        rows.push({actual:result.contentSha256,expected:hash(result.content),observations:result.observations});
      }
      console.log(JSON.stringify({rows,observations:prior.observations}));
    ''')
    assert all(row['actual'] == row['expected'] for row in result['rows'])
    assert all(row['observations'] == result['observations'] for row in result['rows'])


def test_bounds_repair_preserves_observations_without_field_checklist() -> None:
    # Given bounds refused review before producing a checklist, When a semantic
    # replacement omits or forges observations, Then parent observations survive.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-grounding.json','utf8'));
      const rows=[];
      for(const extra of [{},{observations:[{path:'invented.ts',status:'found'}]}]) {
        const result=mergeSemanticMemoryRepairDelta({operations:[fixture.original],newMemories:[]},{operations:[{...fixture.corrected,...extra}],newMemories:[]},[fixture.original.name]);
        rows.push(result.operations[0].observations);
      }
      console.log(JSON.stringify({expected:fixture.original.observations,rows}));
    ''')
    assert all(row == result['expected'] for row in result['rows'])
