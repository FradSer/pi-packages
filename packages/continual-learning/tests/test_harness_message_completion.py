from support import isolated_run_bun


def test_literal_message_completion_only_extends_one_exact_user_quote() -> None:
    value = isolated_run_bun(r'''
      import {completeHarnessLiteralMessages} from './packages/continual-learning/extensions/harness-consolidation.ts';
      const operation={op:'addRule',rule:{id:'block-npm',bash:'^npm(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Do not run npm.'},cases:{positive:[{bash:'npm test'}],negative:[{bash:'pnpm test'}]}};
      const quote='Do not run npm. This lasts for future project tasks.';
      const plan={kind:'harness-consolidation-plan',operations:[operation],evidence:[{index:0,source:'user',quote,count:1,eventIndex:0}]};
      const before=JSON.stringify(plan),completed=completeHarnessLiteralMessages(plan);
      const variants=[{...plan,evidence:[...plan.evidence,...plan.evidence]},
        {...plan,evidence:[{...plan.evidence[0],source:'toolResult'}]},
        {...plan,operations:[{...operation,correction:{priorRevision:'old'}}]},
        {...plan,operations:[{...operation,op:'updateRule'}]},
        {...plan,operations:[{...operation,rule:{...operation.rule,bash:'.*npm.*'}}]},
        {...plan,operations:[{...operation,rule:{...operation.rule,message:'Use pnpm.'}}]},
        {...plan,evidence:[{...plan.evidence[0],quote:quote+' api_key=sk-'+'a'.repeat(45)}]}];
      console.log(JSON.stringify({unchanged:before===JSON.stringify(plan),completed,plan,untouched:variants.map(v=>completeHarnessLiteralMessages(v)===v)}));
    ''')
    assert value['unchanged'] and all(value['untouched'])
    old, new = value['plan'], value['completed']
    assert new['operations'][0]['rule']['message'] == old['evidence'][0]['quote']
    new['operations'][0]['rule']['message'] = old['operations'][0]['rule']['message']
    assert new == old


def test_completion_does_not_authorize_temporary_conditional_or_revoked_rules() -> None:
    value = isolated_run_bun(r'''
      import {completeHarnessLiteralMessages} from './packages/continual-learning/extensions/harness-consolidation.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const results=[];
      for(const [tail,authority,counter] of [['Only for this task.','temporary','compatible'],['Unless I approve.','conditional','compatible'],['For future tasks.','lasting','contradicts']]){
        const quote='Do not run npm. '+tail;
        const p=completeHarnessLiteralMessages({kind:'harness-consolidation-plan',operations:[{op:'addRule',rule:{id:'block-npm',bash:'^npm(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Do not run npm.'}}],evidence:[{index:0,source:'user',quote,count:1,eventIndex:0}]});
        const questions=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{const r=JSON.parse(init.body);questions.push(...Object.keys(r.questions));const answers=Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{const choice=k.startsWith('authority_')?authority:k.startsWith('family_')?'authorized':counter;return[k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===choice?1:0]))}];}));return new Response(JSON.stringify({model:'jev-1.13.0',answers}));}});
        const verdict=await judge.validate('harness',{contextEnabled:true,entries:[{role:'user',content:quote},{role:'user',content:'The prior restriction is permanently revoked.'}]},p.operations,[],undefined,p.evidence);
        results.push({decision:verdict.decision,questions,message:p.operations[0].rule.message,quote});
      }
      console.log(JSON.stringify(results));
    ''')
    for row in value:
        assert row['message'] == row['quote']
        assert row['decision'] == 'propose'
        assert {'authority_0', 'family_0', 'counter_0_0'} <= set(row['questions'])


def test_completed_message_is_the_candidate_reviewed_stored_and_recorded() -> None:
    from pathlib import Path
    from support import run_bun_script
    row = run_bun_script(Path(__file__).with_name('harness-repair-harness.ts'), 'semantic-message-completion')
    assert row['ok'] and row['directApply']['outcome'] == 'applied'
    assert row['spawned'] == 1 and row['semanticCalls'] == 1
    evidence = row['messageCompletionEvidence']
    before, after = evidence['before'], evidence['after']
    message = after['evidence'][0]['quote']
    assert after['operations'][0]['rule']['message'] == message
    assert evidence['judgedOperations'] == [after['operations']]
    assert evidence['stored']['rules'][0]['message'] == message
    import base64
    import hashlib
    import json
    plan_bytes = json.dumps(after, ensure_ascii=False, separators=(',', ':')).encode()
    assert evidence['receipt']['planDigest'] == hashlib.sha256(plan_bytes).hexdigest()
    recorded = evidence['history'][0]['changes'][0]['after']
    recorded_bytes = base64.b64decode(recorded['bytes'])
    assert json.loads(recorded_bytes)['rules'][0]['message'] == message
    assert evidence['receipt']['digestAfter'] == hashlib.sha256(recorded_bytes).hexdigest()
    after['operations'][0]['rule']['message'] = before['operations'][0]['rule']['message']
    assert before == after
