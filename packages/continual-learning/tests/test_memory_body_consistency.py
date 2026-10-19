from hashlib import sha256

from support import isolated_run_bun


def test_real_applied_body_requires_independent_consistency_and_complete_review() -> None:
    rows = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge,jevRepairFailureHints} from './packages/continual-learning/extensions/jev-learning.ts';
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
        rows.push({mode,result,hints:jevRepairFailureHints(result.telemetry),questions:Object.fromEntries(requests.flatMap(r=>Object.entries(r.questions)).filter(([key])=>key==='coherence_0'))});
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
        if row['mode'] in ('contradictory', 'unclear'):
            assert row['result']['telemetry']['candidateFailures'][0]['internalConsistency']
            assert 'internal-consistency' in ' '.join(row['hints'])
        if row['mode'] == 'compatible':
            assert 'coherence_0' in row['result']['candidateReview']['candidates'][0]['passedChecks']


def test_body_coherence_repair_can_update_dependent_description_without_certifying_it() -> None:
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {semanticMemoryRepairFields,mergeSemanticMemoryRepairDelta,distillReviewedNewMemory} from './packages/continual-learning/extensions/inject-memory.ts';
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const evidence={entries:[{role:'user',content:'Established fact.'}]},existing=[];
      const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: Established fact.\ntype: project\n---\nConflicting body.',evidence:[{index:0,quote:'Established fact.'}]};
      const candidates=[candidate],plan={operations:[],newMemories:candidates};
      const review={version:1,purpose:'diagnostic-only',complete:true,sameBatchIndependenceReviewed:false,model:'jev-1.13.0',evidenceDigest:digest(evidence),existingDigest:digest(existing),candidatesDigest:digest(candidates),candidates:[{index:0,candidateDigest:digest(candidate),outcome:'held',passedChecks:['supported_0','supported_description_0','counter_0_0','counter_description_0_0'],heldChecks:['coherence_0']}]};
      const fields=semanticMemoryRepairFields(candidates,review);
      const replacement={...candidate,content:candidate.content.replace('description: Established fact.','description: Corrected reference.').replace('Conflicting body.','Established fact.')};
      const merged=mergeSemanticMemoryRepairDelta(plan,{operations:[],newMemories:[replacement]},['fact.md'],fields,evidence);
      const distilled=distillReviewedNewMemory(plan,candidates,review,evidence,existing,1);
      const scoped=key=>semanticMemoryRepairFields(candidates,{...review,candidates:[{...review.candidates[0],heldChecks:[key]}]});
      console.log(JSON.stringify({fields,merged,distilled,plan,sourceOnly:scoped('supported_0'),counterOnly:scoped('counter_0_0'),descriptionOnly:scoped('supported_description_0'),foreign:scoped('coherence_1')??null,malformed:scoped('coherence_description_0')??null}));
    ''')
    assert value['fields'] == {'fact.md': ['body', 'description']}
    body = value['merged']['newMemories'][0]['content']
    assert 'description: Corrected reference.' in body
    assert body.endswith('Established fact.')
    assert value['sourceOnly'] == value['counterOnly'] == {'fact.md': ['body']}
    assert value['descriptionOnly'] == {'fact.md': ['description']}
    assert value['foreign'] is None and value['malformed'] is None
    assert value['distilled']['names'] == []
    assert value['distilled']['plan'] == value['plan']


def test_actual_v79_description_correction_is_not_restored_after_body_repair() -> None:
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {semanticMemoryRepairFields,mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const f=(await Bun.file('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json').json()).correctionScopeCase;
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const candidate=f.original,candidates=[candidate],plan={operations:[],newMemories:candidates};
      const review={version:1,purpose:'diagnostic-only',complete:true,candidatesDigest:digest(candidates),candidates:[{index:0,candidateDigest:digest(candidate),outcome:'held',passedChecks:['supported_0','supported_description_0','counter_0_0','counter_description_0_0'],heldChecks:['coherence_0']}]};
      const fields=semanticMemoryRepairFields(candidates,review);
      const merged=mergeSemanticMemoryRepairDelta(plan,{operations:[],newMemories:[{...candidate,content:f.submittedContent}]},[candidate.name],fields);
      const actual=merged.newMemories[0];
      console.log(JSON.stringify({fields,exactSubmitted:actual.content===f.submittedContent,oldParentReinserted:f.parentMergedContent!==f.submittedContent,identity:actual.name===candidate.name&&actual.kind===candidate.kind&&actual.classification===candidate.classification,evidence:JSON.stringify(actual.evidence)===JSON.stringify(candidate.evidence),purpose:actual.content.includes('**Why**:')&&actual.content.includes('**How to apply**:')}));
    ''')
    assert value['oldParentReinserted']
    assert value['fields'] == {'limitfunction-type-contract.md': ['body', 'description']}
    assert value['exactSubmitted'] and value['identity'] and value['evidence'] and value['purpose']


def test_real_declaration_body_keeps_assertion_level_and_all_coherence_gates() -> None:
    rows = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-description-body-conflict.json','utf8')).declarationCoherenceCase;
      const rows=[];
      // This is a controlled citation context, not the original complete task.
      const entries=Array.from({length:6},()=>({role:'toolResult',content:''}));
      for(const e of f.original.evidence){entries[e.index].role=e.role;entries[e.index].content+=e.quote+'\n';}
      for(const mode of ['compatible','contradictory','unclear','low-probability','low-confidence','missing','threshold-boundary','bounded-compatible']){
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],...(mode==='bounded-compatible'?{maxRequestBytes:64000}:{}),fetch:async(_url,init)=>{
          const r=JSON.parse(String(init.body));requests.push(r);const answers={};
          for(const [key,q] of Object.entries(r.questions)){
            if(mode==='missing'&&key==='coherence_0')continue;
            const keys=Object.keys(q.criteria);const label=key==='coherence_0'&&['contradictory','unclear'].includes(mode)?mode:keys.find(k=>['grounded','compatible','unrelated'].includes(k))??keys[0];
            const probability=key==='coherence_0'&&mode==='low-probability'?.89:key==='coherence_0'&&mode==='threshold-boundary'?.9:1;
            const confidence=key==='coherence_0'&&mode==='low-confidence'?.79:key==='coherence_0'&&mode==='threshold-boundary'?.8:1;
            const other=keys.find(k=>k!==label);
            answers[key]={type:'choice',choice:label,confidence,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?probability:k===other?1-probability:0]))};
          }
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
        }});
        const candidate={...f.original,content:f.repairedContent};
        const result=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[]);
        const q=requests.flatMap(r=>Object.entries(r.questions)).find(([k])=>k==='coherence_0')[1];
        rows.push({mode,result,question:q,completeBody:q.instructions.candidate.content===f.repairedContent.slice(f.repairedContent.indexOf('\n---\n')+5),allKeys:requests.flatMap(r=>Object.keys(r.questions))});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in rows:
        question = row['question']['instructions']['question']
        if row['mode'] == 'bounded-compatible':
            assert sha256(question.encode()).hexdigest() == '9f139dafbb64cc339fc7800428ed8f925914ac46d94b886eebf7ba75d27fd5e1'
        else:
            assert 'quotation or declaration' in question
            assert 'does not by itself assert runtime behavior' in question
            assert 'Explicit runtime assertions still require comparison' in question
        assert 'adopting a pending promise does not settle' in question
        assert row['completeBody']
        assert 'rejectOnClear?: boolean' in row['question']['instructions']['candidate']['content']
        assert 'supported_0' in row['allKeys']
        assert 'supported_description_0' in row['allKeys']
        assert any(key.startswith('counter_') for key in row['allKeys']), (row['mode'], row['allKeys'])
        assert row['result']['decision'] == ('allow' if row['mode'] in ('compatible', 'threshold-boundary', 'bounded-compatible') else 'propose')


@__import__('pytest').mark.parametrize('mixed_mutation', [False, True])
def test_normal_coherence_uses_complete_bodies_without_external_source_state(mixed_mutation):
    # Given a complete real rejected body and its original evidence,
    # When normal review asks about internal consistency,
    # Then isolate that judgment while retaining every source/counter check.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-body-contradiction.json','utf8'));
      const candidates=[f.candidate];
      const existing=MIXED?[{name:'previous.md',classification:'safe',type:'project',description:'Earlier source.',content:'OLD_BODY_IS_COMPARISON_NOT_INTERNAL_COHERENCE_AUTHORITY'}]:[];
      if(MIXED)candidates.push({...f.candidate,name:'previous.md',kind:'rewrite'});
      const requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
        const r=JSON.parse(String(init.body));requests.push(r);
        const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const keys=Object.keys(q.criteria);
          const label=keys.find(k=>['grounded','compatible','authorized','preserved','supplement','unrelated'].includes(k))??keys[0];
          return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const result=await judge.validate('memory',f.snapshot,candidates,existing);
      console.log(JSON.stringify({result,requests,candidates,sourceEntries:f.snapshot.entries.length}));
    '''.replace('MIXED', str(mixed_mutation).lower()))
    assert result['result']['decision'] == 'allow', result['result']
    coherence = [r for r in result['requests'] if any(k.startswith('coherence_') for k in r['questions'])]
    assert coherence
    seen = set()
    for request in coherence:
        assert all(k.startswith('coherence_') for k in request['questions'])
        import json
        state = json.loads(request['state']) if isinstance(request['state'], str) else request['state']
        assert not set(state).intersection({'frozenEvidence', 'supportEvidence', 'reviewEvidence', 'existingMemories', 'sourceComparisonEvidence', 'mutationComparison', 'currentMaintenanceRequest'})
        assert 'OLD_BODY_IS_COMPARISON_NOT_INTERNAL_COHERENCE_AUTHORITY' not in json.dumps(state)
        for key, question in request['questions'].items():
            index = int(key.removeprefix('coherence_'));seen.add(index)
            candidate = question['instructions']['candidate']
            if 'contentReference' in candidate:
                ref = candidate['contentReference']
                values = [v for v in state[ref['field']] if v['candidateIndex'] == ref['candidateIndex']]
                assert len(values) == 1
                body = values[0][ref['property']]
                expected = result['candidates'][index]['content']
            else:
                import re
                body = candidate['content']
                expected = re.sub(r'^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)', '', result['candidates'][index]['content'])
            assert body == expected
    assert seen == set(range(len(result['candidates'])))
    coverage = [set() for _ in result['candidates']]
    supported = set()
    for request in result['requests']:
        import json,re
        state = json.loads(request['state']) if isinstance(request['state'], str) else request['state']
        for key in request['questions']:
            if re.fullmatch(r'supported_\d+', key):supported.add(int(key.rsplit('_', 1)[1]))
            match = re.fullmatch(r'counter_(\d+)_\d+', key)
            if match:coverage[int(match[1])].update(v['index'] for v in state['reviewEvidence']['entries'])
    assert supported == seen
    assert all(rows == set(range(result['sourceEntries'])) for rows in coverage)
    assert result['result']['telemetry']['requestCount'] == len(result['requests'])
