from support import isolated_run_bun


def test_structured_description_is_grounded_separately_from_unchanged_body() -> None:
    # Given a grounded body and an unsupported index description, the full
    # description must be judged; canonical filenames/types grant no authority.
    values = isolated_run_bun(r'''
      import {loadStructuredDescriptionJudge} from './packages/continual-learning/tests/jev-description-structured-shadow.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const research=await loadStructuredDescriptionJudge();const results=[];
      try {
        for(const unsafe of [false,true])for(const arm of ['before','after']){
          const quote='This project uses pnpm.';const description=unsafe?'All regression tests always pass.':quote;
          const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: ADMINISTRATIVE_NAME\ndescription: ${description}\ntype: project\n---\n${quote}\n`,evidence:[{index:0,quote,role:'user'}]};
          const factory=arm==='before'?research.baselineCreateJevJudge:research.createJevJudge;
          const sent=[];const judge=factory({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            const r=JSON.parse(String(init.body));sent.push(r);const answers={};
            for(const [k,q]of Object.entries(r.questions)){
              const text=q.instructions.candidate.content;const label=k.startsWith('supported')?((text+' '+(q.instructions.candidate.description??'')).includes('always pass')?'unsupported':'grounded'):'compatible';
              answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
            }
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
          const result=await judge.validate('memory',snapshot,[candidate],[]);
          results.push({unsafe,arm,result,meanings:sent.flatMap(r=>Object.values(r.questions).map(q=>q.instructions.candidate)),snapshotUnchanged:snapshot.entries[0].content===quote,candidateUnchanged:candidate.content.includes('ADMINISTRATIVE_NAME')});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in values:
        assert row['result']['decision'] == ('propose' if row['unsafe'] and row['arm'] == 'after' else 'allow')
        if row['unsafe'] and row['arm'] == 'after':
            assert row['result']['telemetry']['reason'] == 'unsupported'
        assert row['snapshotUnchanged'] and row['candidateUnchanged']
        for meaning in row['meanings']:
            assert ('description' in meaning) == (row['arm'] == 'after')
            assert meaning['content'] == 'This project uses pnpm.\n'
            if row['arm'] == 'after':
                assert ('always pass' in meaning['description']) == row['unsafe']
            assert 'This project uses pnpm.' in meaning['content']
            assert 'ADMINISTRATIVE_NAME' not in meaning['content']
            assert 'type: project' not in meaning['content']


def test_structured_description_preserves_body_and_original_privacy_guards() -> None:
    values = isolated_run_bun(r'''
      import {loadStructuredDescriptionJudge} from './packages/continual-learning/tests/jev-description-structured-shadow.ts';
      const research=await loadStructuredDescriptionJudge();const results=[];
      try {
        for(const [mode,header]of [['plain',''],['crlf','---\r\nname: fact\r\ndescription: "Complete description"\r\ntype: project\r\n---\r\n'],['secret','---\nname: fact\ndescription: harmless\napi_key: "SYNTHETIC_SECRET_VALUE"\ntype: project\n---\n']]){
          const body='This project uses pnpm.\nPreserve this complete second line.\n';let calls=0;let meaning;let description;
          const candidate={name:'fact.md',kind:'project',classification:'safe',content:header+body,evidence:[{index:0,quote:body,role:'user'}]};
          const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            calls++;const r=JSON.parse(String(init.body));const answers={};
            for(const [key,q]of Object.entries(r.questions)){meaning=q.instructions.candidate.content;description=q.instructions.candidate.description;const label=key.startsWith('supported')?'grounded':'compatible';answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:body}]},[candidate],[]);
          results.push({mode,calls,result,meaning,description});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in values:
        if row['mode'] == 'secret':
            assert row['calls'] == 0 and row['result']['decision'] == 'propose'
            assert row['result']['telemetry']['reason'] == 'sensitive'
        else:
            assert row['result']['decision'] == 'allow'
            body = 'This project uses pnpm.\nPreserve this complete second line.\n'
            if row['mode'] == 'plain':
                assert row['meaning'] == body
            else:
                assert row['meaning'].endswith(body)
                assert 'Complete description' in row['description']
                assert row['meaning'] == body


def test_structured_description_keeps_complete_first_summary() -> None:
    rows = isolated_run_bun(r'''
      import {loadStructuredDescriptionJudge} from './packages/continual-learning/tests/jev-description-structured-shadow.ts';
      const research=await loadStructuredDescriptionJudge();const results=[];
      try {
        for(const [mode,fields]of [['duplicate','name: fact\ndescription: FIRST_DESCRIPTION\ndescription: SECOND_DESCRIPTION\ntype: project'],['long','name: fact\ndescription: '+ 'x'.repeat(4000)+'TAIL_MARKER\ntype: project'],['absent','name: fact\ntype: project']]){
          const body='This project uses pnpm.\n';let meaning;let description;
          const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            const r=JSON.parse(String(init.body));const answers={};for(const [k,q]of Object.entries(r.questions)){meaning=q.instructions.candidate.content;description=q.instructions.candidate.description;const label=k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:body}]},[{name:'fact.md',kind:'project',classification:'safe',content:'---\n'+fields+'\n---\n'+body,evidence:[{index:0,quote:body,role:'user'}]}],[]);
          results.push({mode,first:description?.includes('FIRST_DESCRIPTION')??false,second:description?.includes('SECOND_DESCRIPTION')??false,tail:description?.includes('TAIL_MARKER')??false,bodyUnchanged:meaning.endsWith(body),exactBody:meaning===body});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in rows:
        assert row['bodyUnchanged'] and row['exactBody']
        if row['mode'] == 'duplicate':
            assert row['first'] and not row['second']
        elif row['mode'] == 'long':
            assert row['tail']
        else:
            assert row['exactBody']


def test_structured_description_leaves_plain_absent_and_harness_wire_identical() -> None:
    rows = isolated_run_bun(r'''
      import {loadStructuredDescriptionJudge} from './packages/continual-learning/tests/jev-description-structured-shadow.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const research=await loadStructuredDescriptionJudge();const results=[];
      try {
        const quote='This project uses pnpm.';
        const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};
        const sample=(await Bun.file('./packages/continual-learning/tests/fixtures/jev-source-development-corpus.json').json())[0];
        const inputs=[{id:'plain',stage:'memory',snapshot,plan:{operations:[{name:'fact.md',kind:'project',classification:'safe',content:quote,evidence:[{index:0,quote,role:'user'}]}]}},{id:'absent',stage:'memory',snapshot,plan:{operations:[{name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]}]}},{id:'harness',stage:'harness',snapshot:sample.snapshot,plan:sample.plan}];
        for(const row of inputs){
          const arms=[];
          for(const factory of [createJevJudge,research.createJevJudge]){
            const requests=[];const judge=factory({enabled:true,apiKey:'fixture',scopes:['memory','harness'],fetch:async(_url,init)=>{
              requests.push(String(init.body));const r=JSON.parse(String(init.body));const answers={};
              for(const [k,q]of Object.entries(r.questions)){
                if(q.type==='noul')answers[k]={type:'noul',noul:.99};
                else {const label=['compatible','same','grounded','lasting','faithful','authorized','unrelated'].find(x=>Object.hasOwn(q.criteria,x));answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
              }
              return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
            }});
            const verdict=await judge.validate(row.stage,row.snapshot,row.plan.operations,[],undefined,row.stage==='harness'?row.plan.evidence:undefined);arms.push({requests,decision:verdict.decision});
          }
          // One documented, authorized delta is allowed in the support question;
          // every other wire byte must stay identical, so undocumented drift
          // still fails. The harness row carries no support question.
          const DELTA=[' A successful tool result that ran the command grounds the claim that the command works for this project.',' A failed, interrupted or erroring run is a transient observation: it does not ground a lasting claim about the command.',' A successful tool result that ran the command counts as that verified observation for the command it ran.'];
          const strip=(value)=>DELTA.reduce((acc,part)=>acc.split(part).join(''),value);
          const productionWire=JSON.stringify(arms[0].requests),shadowWire=JSON.stringify(arms[1].requests);
          results.push({id:row.id,wireIdentical:strip(productionWire)===strip(shadowWire),deltaCount:DELTA.filter(part=>productionWire.includes(part)&&!shadowWire.includes(part)).length,requests:arms[0].requests.length,decisions:arms.map(x=>x.decision)});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in rows:
        assert row['requests'] == 2
        assert row['wireIdentical'] and row['deltaCount'] == (0 if row['id'] == 'harness' else 3) and row['decisions'] == ['allow', 'allow']
