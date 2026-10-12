from support import isolated_run_bun


def test_finite_authority_shadow_retains_all_authorization_and_counter_gates() -> None:
    # Given proven same-project syntax, ask separate lasting permission,
    # message fidelity, argument-family and complete counterevidence questions.
    value = isolated_run_bun(r'''
      import {loadFiniteAuthorityJudge} from './packages/continual-learning/tests/jev-finite-authority-shadow.ts';
      const research=await loadFiniteAuthorityJudge();
      try {
        const row=(await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json())[1];
        const requests=[];
        const judge=research.createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
          const request=JSON.parse(String(init.body));requests.push(request);const answers={};
          for(const [key,q] of Object.entries(request.questions)) {
            if(q.type==='noul')answers[key]={type:'noul',noul:.99};
            else {const label=key.startsWith('authority')?'lasting':key.startsWith('family')?'authorized':key.startsWith('explanation')?'faithful':key.startsWith('counter')?'compatible':'same';answers[key]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
        }});
        const original=JSON.stringify(row);const result=await judge.validate('harness',row.snapshot,row.plan.operations,[],undefined,row.plan.evidence);
        const questions=Object.assign({},...requests.map(r=>r.questions));
        console.log(JSON.stringify({questions,result,unchanged:original===JSON.stringify(row),states:requests.map(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state))}));
      }finally{await research.dispose();}
    ''')
    assert value['unchanged'] and value['result']['decision'] == 'allow'
    assert set(value['questions']) == {'authority_0', 'explanation_0', 'family_0', 'counter_0_0'}
    matching = value['questions']['family_0']['instructions']['candidate']['matching']
    assert '-C .' in matching and 'not proof of user permission' in matching
    assert value['questions']['counter_0_0']['instructions']['candidate']['rule']['matching'] == matching
    assert value['states'][1]['reviewEvidence']['entries'][0]['index'] == 0


def test_finite_family_research_preserves_every_hold_and_unknown_path() -> None:
    value = isolated_run_bun(r'''
      import {loadFiniteAuthorityJudge} from './packages/continual-learning/tests/jev-finite-authority-shadow.ts';
      const fs=(await import('node:fs/promises')).default;
      const sourcePath='./packages/continual-learning/extensions/jev-learning.ts';const originalSource=await fs.readFile(sourcePath,'utf8');
      const research=await loadFiniteAuthorityJudge();const outcomes=[];
      try {
        const base=(await Bun.file('./packages/continual-learning/tests/fixtures/jev-harness-support-corpus.json').json())[1];
        for(const mode of ['conditional','message-extra','family-extra','family-uncertain','counter','unavailable','confirmation','disabled','replace','unknown']) {
          const row=structuredClone(base);const op=row.plan.operations[0];
          if(mode==='confirmation')op.rule.action='confirm';if(mode==='disabled')op.rule.enabled=false;if(mode==='replace')op.op='replaceRule';if(mode==='unknown')op.rule.bash+='|.*';
          const keys=new Set();
          const judge=research.createJevJudge({enabled:true,apiKey:'fixture',defaultModel:'jev-1.13.0',scopes:['harness'],fetch:async(_url,init)=>{
            if(mode==='unavailable')throw Error('Fixture unavailable');const r=JSON.parse(String(init.body));const answers={};
            for(const [key,q] of Object.entries(r.questions)) {
              keys.add(key);if(q.type==='noul')answers[key]={type:'noul',noul:.99};
              else {const label=key.startsWith('authority')?(mode==='conditional'?'conditional':'lasting'):key.startsWith('family')?(mode==='family-extra'?'extra':'authorized'):key.startsWith('explanation')?(mode==='message-extra'?'extra':'faithful'):key.startsWith('counter')?(mode==='counter'?'contradicts':'compatible'):'same';answers[key]={type:'choice',choice:label,confidence:mode==='family-uncertain'&&key.startsWith('family')?.79:.99,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const result=await judge.validate('harness',row.snapshot,row.plan.operations,[],undefined,row.plan.evidence);
          outcomes.push({mode,keys:[...keys],result});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify({outcomes,sourceUnchanged:originalSource===await fs.readFile(sourcePath,'utf8')}));
    ''')
    assert value['sourceUnchanged']
    for row in value['outcomes']:
        if row['mode'] in ('confirmation', 'disabled', 'replace', 'unknown'):
            assert 'supported_0' in row['keys'] and 'expands_0' in row['keys']
            assert 'authority_0' not in row['keys']
        else:
            assert row['result']['decision'] == 'propose'
            assert row['result']['telemetry']['reason'] != 'supported'
