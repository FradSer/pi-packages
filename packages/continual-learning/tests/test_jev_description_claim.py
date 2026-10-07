from support import isolated_run_bun


def test_index_description_is_knowledge_while_name_and_type_are_administrative() -> None:
    # Given a grounded body and an unsupported index description, the full
    # description must be judged; canonical filenames/types grant no authority.
    values = isolated_run_bun(r'''
      import {loadDescriptionClaimJudge} from './packages/continual-learning/tests/jev-description-claim-shadow.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const research=await loadDescriptionClaimJudge();const results=[];
      try {
        for(const unsafe of [false,true])for(const arm of ['before','after']){
          const quote='This project uses pnpm.';const description=unsafe?'All regression tests always pass.':quote;
          const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\nname: ADMINISTRATIVE_NAME\ndescription: ${description}\ntype: project\n---\n${quote}\n`,evidence:[{index:0,quote,role:'user'}]};
          const factory=arm==='before'?research.baselineCreateJevJudge:research.createJevJudge;
          const sent=[];const judge=factory({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            const r=JSON.parse(String(init.body));sent.push(r);const answers={};
            for(const [k,q]of Object.entries(r.questions)){
              const text=q.instructions.candidate.content;const label=k.startsWith('supported')?(text.includes('always pass')?'unsupported':'grounded'):'compatible';
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
            assert ('Memory index description' in meaning['content']) == (row['arm'] == 'after')
            assert 'This project uses pnpm.' in meaning['content']
            assert 'ADMINISTRATIVE_NAME' not in meaning['content']
            assert 'type: project' not in meaning['content']


def test_description_projection_preserves_body_and_original_privacy_guards() -> None:
    values = isolated_run_bun(r'''
      import {loadDescriptionClaimJudge} from './packages/continual-learning/tests/jev-description-claim-shadow.ts';
      const research=await loadDescriptionClaimJudge();const results=[];
      try {
        for(const [mode,header]of [['plain',''],['crlf','---\r\nname: fact\r\ndescription: "Complete description"\r\ntype: project\r\n---\r\n'],['secret','---\nname: fact\ndescription: harmless\napi_key: "SYNTHETIC_SECRET_VALUE"\ntype: project\n---\n']]){
          const body='This project uses pnpm.\nPreserve this complete second line.\n';let calls=0;let meaning;
          const candidate={name:'fact.md',kind:'project',classification:'safe',content:header+body,evidence:[{index:0,quote:body,role:'user'}]};
          const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            calls++;const r=JSON.parse(String(init.body));const answers={};
            for(const [key,q]of Object.entries(r.questions)){meaning=q.instructions.candidate.content;const label=key.startsWith('supported')?'grounded':'compatible';answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          const result=await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:body}]},[candidate],[]);
          results.push({mode,calls,result,meaning});
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
                assert 'Complete description' in row['meaning']


def test_first_index_description_is_complete_and_absent_description_is_unchanged() -> None:
    rows = isolated_run_bun(r'''
      import {loadDescriptionClaimJudge} from './packages/continual-learning/tests/jev-description-claim-shadow.ts';
      const research=await loadDescriptionClaimJudge();const results=[];
      try {
        for(const [mode,fields]of [['duplicate','name: fact\ndescription: FIRST_DESCRIPTION\ndescription: SECOND_DESCRIPTION\ntype: project'],['long','name: fact\ndescription: '+ 'x'.repeat(4000)+'TAIL_MARKER\ntype: project'],['absent','name: fact\ntype: project']]){
          const body='This project uses pnpm.\n';let meaning;
          const judge=research.createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
            const r=JSON.parse(String(init.body));const answers={};for(const [k,q]of Object.entries(r.questions)){meaning=q.instructions.candidate.content;const label=k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
            return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
          }});
          await judge.validate('memory',{contextEnabled:true,entries:[{role:'user',content:body}]},[{name:'fact.md',kind:'project',classification:'safe',content:'---\n'+fields+'\n---\n'+body,evidence:[{index:0,quote:body,role:'user'}]}],[]);
          results.push({mode,first:meaning.includes('FIRST_DESCRIPTION'),second:meaning.includes('SECOND_DESCRIPTION'),tail:meaning.includes('TAIL_MARKER'),bodyUnchanged:meaning.endsWith(body),exactBody:meaning===body});
        }
      }finally{await research.dispose();}
      console.log(JSON.stringify(results));
    ''')
    for row in rows:
        assert row['bodyUnchanged']
        if row['mode'] == 'duplicate':
            assert row['first'] and not row['second']
        elif row['mode'] == 'long':
            assert row['tail']
        else:
            assert row['exactBody']
