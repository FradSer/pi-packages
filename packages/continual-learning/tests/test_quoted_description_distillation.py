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
