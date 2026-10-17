from support import isolated_run_bun


def test_leading_horizontal_space_is_proven_not_delegated_to_regex_inference() -> None:
    # Given the actual held public rule, When its complete matching grammar is
    # recognized, Then code describes syntax while Jev still owns permission.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='Permanent project constraint: Bash commands whose first executable is npm must be blocked; use pnpm instead.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
      const rows=[];
      for(const pattern of ['^[ \\t]*npm(?:[ \\t]|$(?![\\s\\S]))','^[ \\t]*npm(?:[ \\t\\n;|&<>]|$(?![\\s\\S]))','^npm.*','^[\\s]*npm(?:[ \\t]|$(?![\\s\\S]))']){
        const requests=[];
        const candidate={op:'addRule',rule:{id:'no-npm',bash:pattern,action:'block',message:quote}};
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['harness'],fetch:async(_url,init)=>{
          const r=JSON.parse(String(init.body));requests.push(r);
          const answers=Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{
            if(q.type==='noul')return[k,{type:'noul',noul:.99}];
            const choice=k.startsWith('authority')?'lasting':k.startsWith('family')?'authorized':k.startsWith('counter')?'compatible':'same';
            return[k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(c=>[c,c===choice?1:0]))}];
          }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
        }});
        const result=await judge.validate('harness',snapshot,[candidate],[],undefined,[{index:0,source:'user',quote,count:1}]);
        const questions=Object.assign({},...requests.map(r=>r.questions));rows.push({result,keys:Object.keys(questions),matching:questions.family_0?.instructions.candidate.matching,counter:questions.counter_0_0?.instructions.candidate});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in value[:2]:
        assert row['keys'], value
        assert 'family_0' in row['keys'] and 'authority_0' in row['keys']
        assert 'supported_0' not in row['keys']
        assert 'leading' in row['matching'] and 'spaces or tabs' in row['matching']
        assert row['counter']['rule']['matching'] == row['matching']
    assert 'newline' not in value[0]['matching']
    assert 'newline' in value[1]['matching']
    for row in value[2:]:
        assert 'family_0' not in row['keys'] and 'supported_0' in row['keys']


def test_authored_family_example_distinguishes_word_separators_from_command_end() -> None:
    # Given a literal family prohibition, When the documented authoring pattern
    # runs in the real guardrail evaluator, Then a command-ending newline is not
    # mistaken for a newline separating words inside a multiword command.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {evaluateBash,validateRuleDeclaration} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const text=fs.readFileSync('./packages/continual-learning/prompts/harness-consolidator.md','utf8');
      const example=[...text.matchAll(/```json\n([\s\S]*?)\n\s*```/g)].map(m=>JSON.parse(m[1])).find(v=>v.rule?.id==='block-command-family');
      if(!example)throw Error('Missing command-family separator contract');
      const rule=example.rule;const config={rules:[rule],bashEvaluationComplete:true,invalidRules:[]};
      const commands=['npm test','  npm ci','npm\ninstall','npm;echo done','npm|cat','npm>out','npm\r','npm\u00a0test','npmify test',"printf '%s' 'npm test'",'npm() { :; }'];
      const decisions=commands.map(c=>evaluateBash(config,c).decision);
      const multi={...rule,bash:rule.bash.replace('npm','git[ \\t]+push')};
      console.log(JSON.stringify({errors:validateRuleDeclaration(rule),decisions,multi:['git push\npnpm test','git\npush','git\u00a0push'].map(c=>evaluateBash({...config,rules:[multi]},c).decision)}));
    ''')
    assert value['errors'] == []
    assert value['decisions'] == ['block'] * 6 + ['execute'] * 5
    assert value['multi'] == ['block', 'execute', 'execute']


def test_native_acceptance_requires_current_revision_and_actual_guidance_context() -> None:
    from live_harness_first_run import current_guidance_delivered

    rule = {'id': 'guard', 'instructions': 'Apply the current scoped guidance.'}
    expected = [{'id': 'guard', 'revision': 'new'}]
    ledger = {'type': 'custom', 'customType': 'harness-guidance-delivery',
              'data': {'entries': [{'id': 'guard', 'revision': 'new', 'status': 'active'}]}}
    system = {'type': 'message', 'message': {'role': 'system',
              'sections': {'harness_guidance': '[harness:guard] Apply the current scoped guidance.'}}}
    assert current_guidance_delivered([ledger, system], {'rules': [rule]}, expected)
    assert not current_guidance_delivered([ledger], {'rules': [rule]}, expected)
    assert not current_guidance_delivered([system], {'rules': [rule]}, expected)
    assert not current_guidance_delivered([ledger, system], {'rules': [rule]}, [{'id': 'guard', 'revision': 'old'}])
    assert not current_guidance_delivered([ledger, system], {'rules': [{**rule, 'instructions': 'Different instructions.'}]}, expected)


def test_permission_revocation_and_factual_counterevidence_each_hold_the_complete_plan() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='Never run npm in this project.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote},{role:'toolResult',content:'Documentation mentions npm install; this is reference data, not user permission.'}]};
      const candidate={op:'addRule',rule:{id:'no-npm',bash:'^[ \\t]*npm(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:quote}};
      const rows=[];
      for(const held of ['none','policy','facts']){
        const requests=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['harness'],fetch:async(_url,init)=>{
          const r=JSON.parse(String(init.body));requests.push(r);
          const answers=Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{
            const choice=k.startsWith('authority')?'lasting':k.startsWith('family')?'authorized':
              k.startsWith('counter_facts_')?(held==='facts'?'contradicts':'compatible'):
              k.startsWith('counter_')?(held==='policy'?'contradicts':'compatible'):Object.keys(q.criteria)[0];
            return[k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(c=>[c,c===choice?1:0]))}];
          }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
        }});
        const result=await judge.validate('harness',snapshot,[candidate],[],undefined,[{index:0,source:'user',quote,count:1}]);
        const counters=requests.filter(r=>r.state.reviewEvidence);rows.push({held,result,
          checks:counters.flatMap(r=>Object.keys(r.questions)),complete:counters.every(r=>r.state.reviewEvidence.entries.length===2),
          policy:counters[0]?.questions.counter_0_0?.instructions.question,
          facts:counters[0]?.questions.counter_facts_0_0?.instructions.question});
      }
      console.log(JSON.stringify(rows));
    ''')
    assert value[0]['result']['decision'] == 'allow'
    for row in value:
        assert row['complete']
        assert {'counter_0_0', 'counter_facts_0_0'} <= set(row['checks'])
        assert 'original user' in row['policy'] and 'factual' in row['facts']
    for row in value[1:]:
        assert row['result']['decision'] == 'propose'
        assert row['result']['telemetry']['dimension'] == 'counterevidence'
        assert row['result']['telemetry']['evidenceEntryStart'] == 0
        assert row['result']['telemetry']['evidenceEntryEnd'] == 1
