from support import isolated_run_bun


def test_real_successful_edit_patch_can_ground_changed_knowledge() -> None:
    result = isolated_run_bun(r'''
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {normalizeSnapshotEvidence,normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      const {snapshot}=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-correction-relations.json').json();
      const before=JSON.stringify(snapshot),patch=snapshot.entries[33].message.details.patch;
      const rows=patch.split('\n'),line=rows.findIndex(s=>s.startsWith('+')&&s.includes("Pick<LimitFunction, 'clearQueue' | 'onIdle'>"))+1;
      const raw={operations:[],newMemories:[{name:'changed-contract.md',kind:'project',classification:'safe',content:'---\nname: changed-contract\ndescription: Declared wrapper members include onIdle.\ntype: project\n---\nThe edited declaration includes onIdle.',evidence:[{index:33,role:'toolResult',lines:{source:'patch',block:0,start:line,end:line}}]}]};
      let resolved,error;try{resolved=resolveMemoryPlanCitations(raw,snapshot);}catch(e){error=e.message;}
      const shown=locatedMemoryEvidence(snapshot).entries[33].entry.message;
      console.log(JSON.stringify({error,line,quote:rows[line-1],resolved,patch,
        numbered:shown.details.patch.citationLines,unchanged:before===JSON.stringify(snapshot),
        problems:resolved?candidateCitationProblems(snapshot,resolved.newMemories):null,
        normalized:resolved?normalizeNewMemoryProposals(resolved,snapshot):null}));
    ''')
    assert result.get('error') is None
    assert result['resolved']['newMemories'][0]['evidence'] == [
        {'index': 33, 'quote': result['quote'], 'role': 'toolResult'}]
    assert result['quote'].startswith('+')
    assert result['numbered']['source'] == 'patch'
    assert '\n'.join(row['text'] for row in result['numbered']['lines']) == result['patch']
    assert result['unchanged'] and not result['problems']
    assert result['normalized'][0]['evidence'][0]['quote'] == result['quote']


def test_patch_locations_do_not_promote_failed_edits_assistant_arguments_or_other_details() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {normalizeSnapshotEvidence} from './packages/continual-learning/extensions/consolidation-run.ts';
      const good={role:'toolResult',toolName:'edit',isError:false,content:'Edit completed',details:{patch:'-old\r\n+new\r\n'}};
      const snapshot={entries:[good,{...good,role:'assistant'},{...good,isError:true},{...good,isError:undefined},{...good,toolName:'read'},{...good,details:{proposedPatch:good.details.patch}},{...good,details:{patch:'+API_KEY=sk-'+'a'.repeat(48)}},{...good,details:{patch:'x'.repeat(2001)}}]};
      const resolve=(index,lines={source:'patch',block:0,start:2,end:2},role='toolResult')=>{try{return resolveMemoryPlanCitations({operations:[{evidence:[{index,lines,role}]}]},snapshot).operations[0].evidence[0];}catch{return false;}};
      const bad=[...Array.from({length:5},(_,i)=>resolve(i+1)),resolve(6,{source:'patch',block:0,start:1,end:1}),resolve(7,{source:'patch',block:0,start:1,end:1}),resolve(0,{source:'patch',block:1,start:1,end:1}),resolve(0,{source:'arguments',block:0,start:1,end:1}),resolve(0,undefined,'user')];
      let stripped=false;try{normalizeSnapshotEvidence([{index:0,quote:'old\r\nnew'}],snapshot);stripped=true;}catch{}
      console.log(JSON.stringify({good:resolve(0),bad,stripped}));
    ''')
    assert value['good'] == {'index': 0, 'quote': '+new\r', 'role': 'toolResult'}
    assert not any(value['bad']) and not value['stripped']


def test_patch_citations_follow_initial_and_repaired_parent_mutation_paths() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    for reason in ('patch-supported', 'patch-repair'):
        value = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert value['registryReceipt']['operations'] == 1
        assert value['memoryMirrored'] and not value['lock']
        assert value['semanticRepairs'] == (1 if reason == 'patch-repair' else 0)
        assert any(attempt['phase'] == 'memory' and attempt['outcome'] == 'applied'
                   for attempt in value['registryReceipt']['attempts'])
