"""Jev transport recovery: a bounded retry must not invent a result.

The itsdangerous-on arm lost its whole Memory review to three connection-level
failures inside one concurrent round of four requests. These cases cover the
recovery rule, the recorded failure class, and the refusals to retry a
status-bearing failure or a timeout.
"""

from __future__ import annotations

from support import isolated_run_bun

GOOD_ANSWERS = """
        const answers={};
        for(const [key,q] of Object.entries(request.questions)) {
          if(key.startsWith('coherence_')){answers[key]={type:'choice',choice:'compatible',confidence:1,probabilities:{compatible:1,contradictory:0,unclear:0}};continue;}
          if(q.type==='noul') answers[key]={type:'noul',noul:0.99};
          if(q.type==='score') answers[key]={type:'score',score:2.88,confidence:0.95,probabilities:{0:0.01,1:0.01,2:0.07,3:0.91},legend:{0:"a",1:"b",2:"c",3:"d"}};
          if(q.type==='choice') answers[key]=key.startsWith('supported')
            ? {type:'choice',choice:'grounded',confidence:0.99,probabilities:{grounded:1,speculative:0,transient:0,unsupported:0,unclear:0}}
            : {type:'choice',choice:'supplement',confidence:0.99,probabilities:{unrelated:0,duplicate:0,supplement:1,conflict:0,unclear:0}};
        }
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:20}}));
"""


def test_connection_failure_recovers_before_any_decision() -> None:
    # Given a memory review whose first request fails at the connection level and
    # whose second request succeeds, When the judge evaluates the candidate, Then
    # it decides on the recorded answer and reports the retry.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let attempts=0;
      const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async(_url,init)=>{
        attempts++;
        if(attempts===1) throw new Error('PRIVATE PROVIDER ERROR');
        const request=JSON.parse(init.body);
''' + GOOD_ANSWERS + r'''
      }});
      const evidence={entries:[{message:{role:'user',content:'This project uses pnpm.'}}]};
      const candidate={name:'test.md',content:'Use pnpm test.'};
      const existing=[{name:'other.md',classification:'safe',type:'project',description:'Other',content:'Use pnpm.'}];
      const recovered=await judge.validate('memory',evidence,[candidate],existing);
      console.log(JSON.stringify({attempts,recovered}));
    ''')
    assert value['attempts'] == 2
    assert value['recovered']['decision'] == 'allow'
    telemetry = value['recovered']['telemetry']
    assert telemetry['retriedRequests'] == 1
    assert telemetry['requestCount'] == 2 and telemetry['completedRequests'] == 1
    assert 'failureKind' not in telemetry
    assert 'PRIVATE PROVIDER ERROR' not in str(value)


def test_persistent_connection_failure_records_the_class_and_stays_a_proposal() -> None:
    # Given a memory review whose requests keep failing at the connection level,
    # When the judge evaluates the candidate, Then it proposes with the recorded
    # connection class and never leaks provider text.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let attempts=0;
      const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async()=>{
        attempts++;
        throw new Error('PRIVATE PROVIDER ERROR');
      }});
      const failed=await judge.validate('memory','evidence',['candidate'],[]);
      console.log(JSON.stringify({attempts,failed}));
    ''')
    assert value['attempts'] == 2
    telemetry = value['failed']['telemetry']
    assert value['failed']['decision'] == 'propose'
    assert telemetry['reason'] == 'unavailable'
    assert telemetry['failureKind'] == 'connection'
    assert telemetry['retriedRequests'] == 1
    assert telemetry['requestCount'] == 2 and telemetry['completedRequests'] == 0
    assert 'PRIVATE PROVIDER ERROR' not in str(value)


def test_status_failure_and_timeout_are_not_retried() -> None:
    # Given a status-bearing failure and a timeout, When the judge evaluates,
    # Then the HTTP class keeps its status and neither case is retried.
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      let statusAttempts=0;
      const status=await createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',fetch:async()=>{
        statusAttempts++;
        return new Response('PRIVATE DIAGNOSTIC',{status:500});
      }}).validate('memory','evidence',['candidate'],[]);
      let timeoutAttempts=0;
      const timeout=await createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['memory'],apiKey:'fixture',timeout:5,fetch:async(_url,init)=>{
        timeoutAttempts++;
        return new Promise((_resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('private timeout'))));
      }}).validate('memory','evidence',['candidate'],[]);
      console.log(JSON.stringify({statusAttempts,status,timeoutAttempts,timeout}));
    ''')
    assert value['statusAttempts'] == 1
    assert value['status']['decision'] == 'propose'
    assert value['status']['telemetry']['failureKind'] == 'http'
    assert value['status']['telemetry']['httpStatus'] == 500
    assert 'retriedRequests' not in value['status']['telemetry']
    assert value['timeoutAttempts'] == 1
    assert value['timeout']['telemetry']['reason'] == 'timeout'
    assert value['timeout']['telemetry']['failureKind'] == 'timeout'
    assert 'retriedRequests' not in value['timeout']['telemetry']
    assert 'PRIVATE DIAGNOSTIC' not in str(value)

def test_recovered_complete_cited_review_keeps_its_bound_checklist() -> None:
    # Given complete frozen citation windows and one failed transport attempt,
    # When its exact retry succeeds, Then all successful logical requests bind
    # a checklist; a failed attempt remains cost-bearing, not a missing window.
    rows = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const rows=[];
      for(const mode of ['recovered','held','persistent']){
        let attempts=0;
        const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],requestConcurrency:1,fetch:async(_url,init)=>{
          attempts++;if(attempts===1||mode==='persistent'&&attempts===2)throw Error('private transport diagnostic');
          const request=JSON.parse(String(init.body)),answers={};
          for(const [key,q]of Object.entries(request.questions)){
            const choices=Object.keys(q.criteria);
            const choice=key.startsWith('supported')?'grounded':'compatible';
            const held=mode==='held'&&key==='counter_0_1';
            answers[key]={type:'choice',choice,confidence:held?.7:1,probabilities:Object.fromEntries(choices.map(c=>[c,c===choice?held?.85:1:c==='unclear'&&held?.15:0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:100,output_tokens:10}}));
        }});
        const quote='The public project uses pnpm.';
        const evidence={contextEnabled:true,entries:[{role:'user',content:quote},{role:'toolResult',content:'Public unrelated source. '.repeat(900)}]};
        const candidates=[{name:'project.md',kind:'project',classification:'safe',content:`---\nname: Project\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,role:'user',quote}]}];
        const result=await judge.validate('memory',evidence,candidates,[]);
        rows.push({mode,attempts,result});
      }console.log(JSON.stringify(rows));
    ''')
    recovered, held, persistent = rows
    assert recovered['result']['decision'] == 'allow'
    review = recovered['result'].get('candidateReview')
    assert review and review['complete']
    assert review['counterWindows'] == [[0], [1]]
    assert review['candidates'][0]['outcome'] == 'passed'
    telemetry = recovered['result']['telemetry']
    assert telemetry['requestCount'] == telemetry['completedRequests'] + 1
    assert telemetry['retriedRequests'] == 1
    assert telemetry['coveredEntries'] == telemetry['evidenceEntries'] == 2
    assert held['result']['decision'] == 'propose'
    assert held['result']['candidateReview']['complete']
    assert held['result']['candidateReview']['candidates'][0]['outcome'] == 'held'
    assert persistent['result']['decision'] == 'propose'
    assert 'candidateReview' not in persistent['result']
    assert 'private transport diagnostic' not in str(rows)
