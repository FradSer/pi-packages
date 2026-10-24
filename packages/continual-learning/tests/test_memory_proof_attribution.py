import json
from pathlib import Path

from support import isolated_run_bun


def test_real_rewrite_preserves_contract_without_inheriting_unobserved_proof() -> None:
    # Given the complete v20 failure, the test exists in source but was never
    # observed in this slice. Old Memory is not evidence of that test assertion.
    fixture = json.loads((Path(__file__).parent / 'fixtures/real-memory-proof-attribution-gap.json').read_text())
    entries = fixture['dossier']['taskSlice']['entries']
    assert len(entries) == 63
    results = [entry['message'] for entry in entries if entry.get('message', {}).get('role') == 'toolResult']
    assert not any('expectError(limitFunction' in json.dumps(result) for result in results)
    assert 'expectError(limitFunction' in fixture['repaired']['operations'][0]['content']
    assert 'PromiseLike<ReturnType>' in json.dumps(results)
    assert 'pLimit(1,{rejectOnClear:true})' in json.dumps(entries)
    assert 'queued.isFulfilled===undefined' in json.dumps(entries)

    # When either initial planning or the existing bounded repair runs, Then
    # both retain original-source attribution and predecessor preservation.
    # Initial generation uses its refs-only template; repair retains the
    # detailed legacy guidance. This tests delivery, not learning benefit.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let captured;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        captured=input.prompt;return {text:'{}',exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {buildIncrementalMemoryConsolidatorPrompt}=await import('./packages/continual-learning/extensions/planner-prompts.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-proof-attribution-gap.json').json();
      await repairIncrementalMemoryPlan({identity:f.original,rejectedPlan:f.original,
        errors:['support uncertainty'],selectedNames:f.dossier.selectedMemories.map(x=>x.name),
        repairableNames:f.original.operations.map(x=>x.name),
        repairableFields:Object.fromEntries(f.original.operations.map(x=>[x.name,['body','description']])),
        semanticContext:{existingMemories:f.dossier.selectedMemories,frozenEvidence:{entries:f.dossier.taskSlice.entries}}});
      const initial=buildIncrementalMemoryConsolidatorPrompt({runId:'run',scopeKey:'scope',scopeDigest:'digest',artifactHash:'artifact',snapshotDigest:'snapshot',dossierPath:'/tmp/dossier.json'});
      const payload=JSON.parse(captured.split('\n').at(-1));
      console.log(JSON.stringify({initial,repair:captured.slice(0,captured.lastIndexOf('\n')),
        completeEvidence:payload.semanticContext.frozenEvidence.entries.length===63,
        predecessorPreserved:JSON.stringify(payload.semanticContext.existingMemories)===JSON.stringify(f.dossier.selectedMemories)}));
    ''')
    assert result['completeEvidence'] and result['predecessorPreserved']
    initial, repair = result['initial'], result['repair']
    for prompt in (initial, repair):
        assert 'Select original spans for each factual clause and its premises' in prompt
        assert 'Preserve still-valid predecessor knowledge and explicit restrictions' in prompt
    assert 'only eligible\nuser/toolResult text can be cited' in initial
    assert 'Current explicit corrections and verified changed project behavior supersede' in initial
    assert 'A claimed fix requires its actual successful verification' in initial
    assert 'Read a diagnostic\'s executed operations before interpreting its printed labels' in initial
    assert 'Preserve supported knowledge, not unsupported proof attribution' not in initial
    assert 'Preserve supported knowledge, not unsupported proof attribution' in repair
    assert 'A test assertion copied from existing Memory is not an observed test' in repair
    assert 'pair the actual invocation with its result' in repair
    assert 'deadlock, unawaited Promise, nonexistent property' in repair
