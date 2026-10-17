from support import isolated_run_bun


def test_configured_request_concurrency_preserves_complete_review_and_bounds() -> None:
    # Given a low-capacity service and complete source evidence,
    # When request concurrency is reduced, Then all original checks still run with the same thresholds.
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const rows=[];
      for(const concurrency of [1,2,4]){
        let active=0,peak=0,calls=0;
        const snapshot={contextEnabled:true,entries:[{role:'user',content:'This project uses pnpm.'},{role:'toolResult',content:'Unrelated public source observation. '.repeat(900)}]};
        const candidate={name:'updates.md',kind:'project',classification:'safe',content:'---\nname: updates\ndescription: This project uses pnpm.\ntype: project\n---\nThis project uses pnpm.',evidence:[{index:0,quote:'This project uses pnpm.',role:'user'}]};
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],requestConcurrency:concurrency,fetch:async(_url,init)=>{
          calls++;active++;peak=Math.max(peak,active);await Promise.resolve();
          const r=JSON.parse(String(init.body)),answers={};
          for(const [k,q]of Object.entries(r.questions)){const label=k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
          active--;return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
        }});
        const result=await judge.validate('memory',snapshot,[candidate],[]);rows.push({concurrency,peak,calls,result});
      }
      const rejected=[];for(const requestConcurrency of [0,5,1.5,'1']){try{createJevJudge({requestConcurrency});rejected.push(false)}catch{rejected.push(true)}}
      console.log(JSON.stringify({rows,rejected}));
    ''')
    assert all(rows['rejected'])
    assert len({r['calls'] for r in rows['rows']}) == 1
    assert rows['rows'][0]['peak'] == 1
    assert rows['rows'][-1]['peak'] > 1
    for row in rows['rows']:
        assert row['peak'] <= row['concurrency']
        assert row['calls'] >= 3
        assert row['result']['decision'] == 'allow'
        telemetry = row['result']['telemetry']
        assert telemetry['completedRequests'] == telemetry['requestCount'] == row['calls']
        assert telemetry['completedWindows'] == telemetry['evidenceWindows']
        assert telemetry['coveredEntries'] == telemetry['evidenceEntries']


def test_persisted_request_concurrency_is_explicit_bounded_configuration() -> None:
    rows = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {readJevConfigState} from './packages/continual-learning/extensions/config.ts';
      const rows=[];for(const value of [null,1,2,4,0,5,1.5,'1']){
        const jev={model:'jev-1.13.0',...(value===null?{}:{requestConcurrency:value})};
        fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({jev}));
        const state=readJevConfigState();rows.push({value,invalid:state.invalid??null,concurrency:state.config?.requestConcurrency??null});
      }console.log(JSON.stringify(rows));
    ''')
    for row in rows:
        valid = row['value'] in (None, 1, 2, 4) and not isinstance(row['value'], str)
        assert row['invalid'] == (None if valid else 'invalid-config')
        if valid:
            assert row['concurrency'] == row['value']


def test_single_request_batches_cover_question_splits_relations_and_readiness() -> None:
    row = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let active=0,peak=0,calls=0;
      const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['selection','memory'],requestConcurrency:1,independentMemoryApplication:true,composedMemoryApplication:true,fetch:async(_url,init)=>{
        calls++;active++;peak=Math.max(peak,active);await Promise.resolve();
        const r=JSON.parse(String(init.body)),answers={};for(const [k,q]of Object.entries(r.questions)){
          if(q.type==='noul'){answers[k]={type:'noul',noul:0.99};continue;}
          if(q.type==='score'){answers[k]={type:'score',score:3,confidence:1,probabilities:{0:0,1:0,2:0,3:1},legend:{0:'a',1:'b',2:'c',3:'d'}};continue;}
          const label=Object.keys(q.criteria)[0];answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};
        }active--;return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const evidence={contextEnabled:true,entries:[{role:'user',content:'This project uses pnpm.'}]};
      const metadata=Array.from({length:40},(_,i)=>({name:`fact-${i}.md`,classification:'safe',type:'project',description:'This project uses pnpm.'}));
      const selection=await judge.select(evidence,metadata,true),splitCalls=calls;
      const candidates=metadata.slice(0,3).map(x=>({name:x.name,kind:'project',classification:'safe',content:`---\nname: ${x.name}\ndescription: This project uses pnpm.\ntype: project\n---\nThis project uses pnpm.`,evidence:[{index:0,quote:'This project uses pnpm.',role:'user'}]}));
      const validation=await judge.validate('memory',evidence,candidates,[]);
      const start=calls,relations=await judge.reviewMemoryRelations(evidence,candidates,[],validation.candidateReview);
      console.log(JSON.stringify({peak,splitCalls,selection,validation,relationAndReadinessCalls:calls-start,relations}));
    ''')
    assert row['peak'] == 1
    assert row['splitCalls'] >= 2 and len(row['selection']['selection']['selected']) == 40
    assert row['validation']['decision'] == 'allow'
    assert row['relationAndReadinessCalls'] == 6
    assert row['relations']['telemetry']['completedRequests'] == 3
    assert row['relations']['readinessTelemetry']['completedRequests'] == 3
    assert len(row['relations']['review']['pairs']) == 3
    assert len(row['relations']['readiness']['candidates']) == 3
