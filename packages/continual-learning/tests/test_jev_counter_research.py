from support import isolated_run_bun


def test_counter_research_changes_only_counter_question_and_preserves_all_holds() -> None:
    # Given original cited inputs, when narrowing the counter question, then
    # independent support/scope and complete-review holds still govern writes.
    value = isolated_run_bun(r'''
      import {counterEvidenceRequest} from './packages/continual-learning/tests/jev-counter-evidence-shadow.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const base=await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json();
      const outcomes=[];
      for(const mode of ['supported','unsupported','scope','counter','unclear','unavailable']) {
        const row=base[1];const sent=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
          if(mode==='unavailable')throw Error('fixture');
          const request=JSON.parse(String(init.body));const before=JSON.stringify(request);const patched=counterEvidenceRequest(request);sent.push({request,patched,unchanged:before===JSON.stringify(request)});
          const answers={};for(const [k,q]of Object.entries(patched.questions)) {
            if(q.type==='noul')answers[k]={type:'noul',noul:mode==='unsupported'?.01:.99};
            else {const label=k.startsWith('counter')?(mode==='counter'?'contradicts':mode==='unclear'?'unclear':'compatible'):mode==='scope'?'broader':'same';answers[k]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        outcomes.push({mode,result:await judge.validate('harness',row.snapshot,row.plan.operations,[],undefined,row.plan.evidence),sent});
      }
      process.stdout.write(JSON.stringify(outcomes));
    ''')
    for row in value:
        assert row['result']['decision'] == ('allow' if row['mode'] == 'supported' else 'propose')
        for sent in row['sent']:
            assert sent['unchanged']
            assert sent['request']['state'] == sent['patched']['state']
            assert sent['request']['model'] == sent['patched']['model']
            assert sent['request']['questions'].keys() == sent['patched']['questions'].keys()
            for key, question in sent['request']['questions'].items():
                patched = sent['patched']['questions'][key]
                if key.startswith('counter_'):
                    assert question['criteria'] == patched['criteria']
                    assert question['instructions']['candidate'] == patched['instructions']['candidate']
                    assert 'earlier condition' in patched['instructions']['question']
                    assert 'verified observation' in patched['instructions']['question']
                else:
                    assert question == patched


def test_counter_research_rejects_conflicting_live_and_preflight_modes() -> None:
    result = isolated_run_bun(r'''
      process.argv=['bun','research','--live','--preflight-only'];
      await import('./packages/continual-learning/tests/evaluate_jev_counter_evidence.ts');
    ''', env={'TYPESAFE_API_KEY': ''}, parse=False)
    assert result.returncode != 0
    assert 'Research modes are mutually exclusive' in result.stderr
