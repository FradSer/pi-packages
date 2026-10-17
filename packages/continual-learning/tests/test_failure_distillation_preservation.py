from support import isolated_run_bun


def test_actual_repaired_failure_body_and_sources_survive_optional_distillation() -> None:
    # Given a historical real correction scopes failure to the last observed source state,
    # When optional distillation runs with the original description's checklist,
    # Then the corrected body and citations survive rather than reverting to
    # the original causal description. Replay the exact historical candidates,
    # not current admission: their self-citations are now rejected below.
    # This proves preservation only, never semantics or mutation authority.
    result = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {distillReviewedNewMemory} from './packages/continual-learning/extensions/inject-memory.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-failure-distillation-overwrite.json').json();
      const candidates=[...f.originalPlan.operations,...f.originalPlan.newMemories];
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const name='onidle_absent_from_index_d_ts.md';
      const repaired=f.repairResponse.newMemories.find(x=>x.name===name);
      const original=candidates.find(x=>x.name===name);
      const run=item=>distillReviewedNewMemory({operations:[],newMemories:[item]},candidates,f.review,f.snapshot,f.existingMemories,11);
      const changed=run(repaired), unchanged=run(original);
      const citationOnly=run({...original,evidence:repaired.evidence});
      console.log(JSON.stringify({boundCandidates:digest(candidates)===f.review.candidatesDigest,
        boundEvidence:digest(f.snapshot)===f.review.evidenceDigest,boundExisting:digest(f.existingMemories)===f.review.existingDigest,
        original,repaired,changed,unchanged,citationOnly,actual:f.actualDistilledPlan.newMemories.find(x=>x.name===name)}));
    ''')
    assert result['boundCandidates'] and result['boundEvidence'] and result['boundExisting']
    assert 'last observed state' in result['repaired']['content']
    assert 'last observed state' not in result['actual']['content']
    assert result['changed']['names'] == []
    assert result['changed']['plan']['newMemories'][0] == result['repaired']
    assert result['citationOnly']['names'] == []
    assert result['citationOnly']['plan']['newMemories'][0]['evidence'] == result['repaired']['evidence']
    assert result['unchanged']['names'] == []
    assert result['unchanged']['plan']['newMemories'][0] == result['original']


def test_historical_full_failure_plan_is_rejected_for_memory_self_evidence() -> None:
    # Given the unchanged original v14 plan and repair now fail provenance,
    # When current parent admission runs, Then no old review or positive fake
    # judge can authorize them. Do not change citations or drop failing cases
    # to revive the former positive coverage claim.
    result = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const file='./packages/continual-learning/tests/fixtures/real-failure-distillation-overwrite.json';
      const bytes=await Bun.file(file).text(),f=JSON.parse(bytes);
      let originalError,repairError;
      try{normalizeNewMemoryProposals(f.originalPlan,f.snapshot)}catch(e){originalError=e.message}
      try{resolveMemoryPlanCitations(f.repairResponse,f.snapshot)}catch(e){repairError=e.message}
      let calls=0;const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>{calls++;throw Error('Must reject before transport')}});
      const verdict=await judge.validate('memory',f.snapshot,[...f.originalPlan.operations,...f.originalPlan.newMemories],f.existingMemories);
      const digest=text=>createHash('sha256').update(text).digest('hex');
      console.log(JSON.stringify({originalError,repairError,calls,verdict:verdict.decision,reason:verdict.telemetry.reason,unchanged:digest(bytes)===digest(await Bun.file(file).text()),entries:f.snapshot.entries.length,candidates:f.originalPlan.operations.length+f.originalPlan.newMemories.length}));
    ''')
    assert 'Memory readback is context, not independent evidence' in result['originalError']
    assert 'memory-reference-not-independent' in result['repairError']
    assert result['calls'] == 0 and result['verdict'] != 'allow'
    assert result['reason'] == 'invalid-response' and result['unchanged']
    assert result['entries'] == 51 and result['candidates'] > 0
