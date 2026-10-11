from __future__ import annotations
from support import isolated_run_bun


def test_owned_correction_requires_exact_semantic_approval_and_user_evidence() -> None:
    value = isolated_run_bun(r'''
      import {validateHarnessPlan, correctionDigest} from './packages/continual-learning/extensions/harness-consolidation.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const prior={id:'learned-test',bash:'^pnpm test',action:'block',message:'Old mistaken block'};
      const quote='Correction: learned-test must allow pnpm test; retire this learned restriction permanently.';
      const snapshot={entries:[{message:{role:'user',content:quote}}]};
      const op={op:'updateRule',rule:{...prior,enabled:false},correction:{eventIndex:0,quote,priorRevision:ruleRevision(prior)},
        cases:{positive:[{bash:'pnpm test',expected:'execute'}],negative:[{bash:'printf safe'}]}};
      const plan={kind:'harness-consolidation-plan',operations:[op],evidence:[{index:0,eventIndex:0,source:'user',quote,count:1}]};
      const options={automatic:true,snapshot,layers:[{source:'project',rules:[prior]}],learnedRules:{[prior.id]:ruleRevision(prior)}};
      const approved={...options,reviewedCorrections:{[prior.id]:correctionDigest(op)}};
      const errors=(p=plan,o=approved)=>validateHarnessPlan(p,o);
      console.log(JSON.stringify({approved:errors(),unreviewed:errors(plan,options),
        manual:errors(plan,{...approved,learnedRules:{}}),
        changed:errors({...plan,operations:[{...op,rule:{...op.rule,message:'changed after review'}}]}),
        assistant:errors(plan,{...approved,snapshot:{entries:[{message:{role:'assistant',content:quote}}]}}),
        tool:errors(plan,{...approved,snapshot:{entries:[{message:{role:'toolResult',content:quote}}]}})}));
    ''')
    assert value['approved'] == []
    for key in ('unreviewed','manual','changed','assistant','tool'):
        assert value[key], (key,value)


def test_owned_text_retirement_uses_prior_selector_as_scope() -> None:
    value = isolated_run_bun(r'''
      import {validateHarnessPlan, correctionDigest} from './packages/continual-learning/extensions/harness-consolidation.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const prior={id:'learned-label',text:'release checklist',instructions:'Always include this checklist.'};
      const quote='Permanently retire learned-label; the release checklist is obsolete.';
      const op={op:'updateRule',rule:{...prior,enabled:false},correction:{eventIndex:0,quote,priorRevision:ruleRevision(prior)},cases:{positive:[{text:['release checklist']}],negative:[{text:['unrelated prose']}]}};
      console.log(JSON.stringify(validateHarnessPlan({kind:'harness-consolidation-plan',operations:[op],evidence:[{index:0,eventIndex:0,source:'user',quote,count:1}]},{automatic:true,snapshot:{entries:[{message:{role:'user',content:quote}}]},layers:[{source:'project',rules:[prior]}],learnedRules:{[prior.id]:ruleRevision(prior)},reviewedCorrections:{[prior.id]:correctionDigest(op)}})));
    ''')
    assert value == []
