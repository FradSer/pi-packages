from support import isolated_run_bun


def test_real_applied_body_requires_independent_consistency_and_complete_review() -> None:
    rows = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-body-contradiction.json','utf8'));
      const rows=[];
      for(const mode of ['contradictory','unclear','compatible','missing']){
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
          const r=JSON.parse(String(init.body));requests.push(r);const answers={};
          for(const [key,q] of Object.entries(r.questions)){
            if(mode==='missing'&&key==='coherence_0')continue;
            const keys=Object.keys(q.criteria);const label=key==='coherence_0'?mode:keys.find(k=>['grounded','compatible','unrelated'].includes(k))??keys[0];
            answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?1:0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
        }});
        const result=await judge.validate('memory',f.snapshot,[f.candidate],[]);
        rows.push({mode,result,questions:Object.fromEntries(requests.flatMap(r=>Object.entries(r.questions)).filter(([key])=>key==='coherence_0'))});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in rows:
        assert 'coherence_0' in row['questions']
        body = row['questions']['coherence_0']['instructions']['candidate']['content']
        assert 'nothing in this path' in body and 'adopts whatever' in body
        assert 'adopting a pending promise does not settle' in row['questions']['coherence_0']['instructions']['question']
        assert row['result']['decision'] == ('allow' if row['mode'] == 'compatible' else 'propose')
        if row['mode'] == 'contradictory':
            assert row['result']['telemetry']['candidateFailures'][0]['candidateIndex'] == 0
            assert row['result']['telemetry']['candidateFailures'][0]['reason'] == 'unsupported'
        if row['mode'] == 'compatible':
            assert 'coherence_0' in row['result']['candidateReview']['candidates'][0]['passedChecks']


def test_coherence_hold_repairs_only_body_and_keeps_reviewed_description() -> None:
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {semanticMemoryRepairFields,mergeSemanticMemoryRepairDelta,distillReviewedNewMemory} from './packages/continual-learning/extensions/inject-memory.ts';
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const evidence={entries:[{role:'user',content:'Established fact.'}]},existing=[];
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: Established fact.\ntype: project\n---\nConflicting body.',evidence:[{index:0,quote:'Established fact.'}]};
      const candidates=[candidate],plan={operations:[],newMemories:candidates};
      const review={version:1,purpose:'diagnostic-only',complete:true,sameBatchIndependenceReviewed:false,model:'jev-1.13.0',evidenceDigest:digest(evidence),existingDigest:digest(existing),candidatesDigest:digest(candidates),candidates:[{index:0,candidateDigest:digest(candidate),outcome:'held',passedChecks:['supported_0','supported_description_0','counter_0_0','counter_description_0_0'],heldChecks:['coherence_0']}]};
      const fields=semanticMemoryRepairFields(candidates,review);
      const replacement={...candidate,content:candidate.content.replace('description: Established fact.','description: Unreviewed new claim.').replace('Conflicting body.','Established fact.')};
      const merged=mergeSemanticMemoryRepairDelta(plan,{operations:[],newMemories:[replacement]},['fact.md'],fields,evidence);
      const distilled=distillReviewedNewMemory(plan,candidates,review,evidence,existing,1);
      console.log(JSON.stringify({fields,merged,distilled,plan}));
    ''')
    assert value['fields'] == {'fact.md': ['body']}
    body = value['merged']['newMemories'][0]['content']
    assert 'description: Established fact.' in body and 'Unreviewed new claim' not in body
    assert body.endswith('Established fact.')
    assert value['distilled']['names'] == []
    assert value['distilled']['plan'] == value['plan']
