from support import isolated_run_bun


def test_parent_rejects_memory_readback_as_independent_support_for_all_citation_forms() -> None:
    value = isolated_run_bun(r'''
      import {normalizeSnapshotEvidence} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {locatedMemoryEvidence,resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const body='The device still runs the old deployment.';
      const calls=[{name:'codemode',arguments:{code:String.raw`const root="C:\\isolated-agent\\memory\\--project--"; await tools.read({path:root+"\\deployment.md"});`}},{name:'bash',arguments:{command:'cat .memory/deployment.md'}},{name:'codemode',arguments:{code:'await tools.read({path:".memory/deployment.md"})'}},...['.memory/deployment.md','memory/--project--/deployment.md',String.raw`C:\Users\test\.pi\agent\memory\--project--\deployment.md`,String.raw`C:\isolated-agent\memory\--project--\deployment.md`].map(path=>({name:'read',arguments:{path}})),{name:'read',arguments:{path:'/project/.memory/deployment.md'}},
        {name:'read',arguments:{path:'/home/.pi/agent/memory/--project--/deployment.md'}},
        {name:'codemode',arguments:{code:'const pub="/project/.memory"; const har="/home/.pi/agent/memory/--project--"; await tools.read({path:pub+"/deployment.md"}); await tools.read({path:"/project/runtime/shell/main.js"});'}},
        {name:'bash',arguments:{command:'cat /project/.memory/deployment.md; cat /project/runtime/shell/main.js'}}];
      const rows=calls.map((call,index)=>{
        const snapshot={entries:[{role:'assistant',content:[{type:'toolCall',id:'read-memory',...call}]},{role:'toolResult',toolCallId:'read-memory',toolName:call.name,isError:false,content:body}]};
        const before=JSON.stringify(snapshot);const shown=locatedMemoryEvidence(snapshot);
        const rejected=[];
        for(const citation of [{index:1,quote:body},{index:1,lines:{block:0,start:1,end:1}},{ref:'e1.b0.l1'}]){
          try{const plan=resolveMemoryPlanCitations({operations:[{evidence:[citation]}]},snapshot);normalizeSnapshotEvidence(plan.operations[0].evidence,snapshot);rejected.push(false);}catch{rejected.push(true);}
        }
        return {rejected,eligible:shown.entries[1].citationEligible,context:shown.entries[1].entry.content,unchanged:JSON.stringify(snapshot)===before};
      });console.log(JSON.stringify(rows));
    ''')
    assert all(all(row['rejected']) for row in value)
    assert all(row['eligible'] is False for row in value)
    assert all(row['context'] == 'The device still runs the old deployment.' and row['unchanged'] for row in value)


def test_project_source_user_correction_and_observed_read_failure_keep_their_evidence() -> None:
    value = isolated_run_bun(r'''
      import {normalizeSnapshotEvidence} from './packages/continual-learning/extensions/consolidation-run.ts';
      const body='The current source uses ODK_WORKSPACE.';
      const snapshots=[{entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'write',arguments:{path:'/project/README.md',content:'Read .memory/deployment.md'}}]},{role:'toolResult',toolName:'write',toolCallId:'source',isError:false,content:body}]},{entries:[{role:'user',content:body}]},
        {entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:'/project/src/memory-reader.ts'}}]},{role:'toolResult',toolName:'read',toolCallId:'source',isError:false,content:body}]},
        {entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:'/project/README.md'}}]},{role:'toolResult',toolName:'read',toolCallId:'source',isError:false,content:'The project indexes .memory files.'}]},
        {entries:[{role:'assistant',content:[{type:'toolCall',id:'source',name:'read',arguments:{path:'/project/.memory/missing.md'}}]},{role:'toolResult',toolName:'read',toolCallId:'source',isError:true,content:'ENOENT: observation failed'}]}];
      const accepted=snapshots.map(snapshot=>{const index=snapshot.entries.length-1;try{return normalizeSnapshotEvidence([{index,quote:snapshot.entries[index].content}],snapshot).length===1;}catch{return false;}});
      console.log(JSON.stringify({accepted}));
    ''')
    assert all(value['accepted'])


def test_python_memory_provenance_matches_paths_and_actual_call_identity() -> None:
    import runpy
    from pathlib import Path

    namespace = runpy.run_path(str(Path(__file__).parents[1] / 'scripts' / 'validate-consolidate.py'))
    classify = namespace['memory_reference_results']
    paths = ['.memory/deployment.md', 'memory/--project--/deployment.md',
             r'C:\Users\test\.pi\agent\memory\--project--\deployment.md',
             r'C:\isolated-agent\memory\--project--\deployment.md',
             'file:///project/.memory/deployment.md', r'const root="C:\\isolated-agent\\memory\\--project--";']
    for path in paths:
        call = {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'm', 'name': 'read', 'arguments': {'path': path}}]}
        result = {'role': 'toolResult', 'toolName': 'read', 'toolCallId': 'm', 'isError': False, 'content': 'old claim'}
        assert classify([call, result]) == {1}
        assert classify([result, call]) == set()
        assert classify([call, {**result, 'toolCallId': 'another'}]) == set()
        assert classify([call, {**result, 'toolName': 'bash'}]) == set()
        assert classify([call, {**result, 'isError': True}]) == set()
    source_write = {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 's', 'name': 'write', 'arguments': {'path': '/project/README.md', 'content': 'Read .memory/deployment.md'}}]}
    assert classify([source_write, {'role': 'toolResult', 'toolName': 'write', 'toolCallId': 's', 'content': 'Success'}]) == set()
