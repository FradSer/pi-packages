import hashlib

from support import isolated_run_bun


def test_real_failed_correction_never_compares_a_proposal_with_itself() -> None:
    value = isolated_run_bun(r'''
      const {createJevJudge}=await import(process.env.CL_RELATION_MODULE??'./packages/continual-learning/extensions/jev-learning.ts');
      import {normalizeNewMemoryProposals,containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const {snapshot,plan,existing}=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-correction-relations.json').json();
      const candidates=[...plan.operations,...normalizeNewMemoryProposals(plan,snapshot,plan.selected)];
      const requests=[];
      await createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const request=JSON.parse(init.body);requests.push(request);
        const answers=Object.fromEntries(Object.entries(request.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'unrelated':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
      }}).validate('memory',snapshot,candidates,existing);
      const relation=requests.filter(r=>Object.keys(r.questions).some(k=>k.startsWith('relation_')));
      const rows=relation.map(r=>{const state=(typeof r.state === "string" ? JSON.parse(r.state) : r.state);return {keys:Object.keys(r.questions),hasProposals:Object.hasOwn(state,'proposedMemoryOperations'),comparatorsExact:JSON.stringify(state.existingMemories)===JSON.stringify(existing)}});
      const counter=requests.flatMap(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state).reviewEvidence?.entries.map(e=>e.index)??[]);
      console.log(JSON.stringify({rows,counter:[...new Set(counter)].sort((a,b)=>a-b),entries:snapshot.entries.length,existing,sensitive:containsSensitiveMemoryMaterial(JSON.stringify({snapshot,plan,existing}))}));
    ''')
    assert value['rows']
    assert not value['sensitive']
    for row in value['rows']:
        assert all(key.startswith('relation_') for key in row['keys'])
        assert 'relation_0' not in row['keys'] and 'relation_description_0' not in row['keys']
        assert not row['hasProposals']
        assert row['comparatorsExact']
    # Preserve raw indexes while excluding only this frozen fixture's own injected reference.
    assert value['entries'] == 42
    assert value['counter'] == [i for i in range(42) if i != 1]


def test_rewrite_excludes_only_its_predecessor_and_preserves_mutation_checks() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const body=(name,text)=>`---\nname: ${name}\ndescription: ${text}\ntype: project\n---\n${text}`;
      const existing=[{name:'contract.md',classification:'safe',content:body('contract','The wrapper has clearQueue.')},{name:'other.md',classification:'safe',content:body('other','Use FIFO.') }];
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Correct contract.md: the wrapper now also exposes onIdle; keep FIFO.'},{role:'toolResult',content:'onIdle and clearQueue are declared; FIFO remains.'}]};
      const candidate={name:'contract.md',kind:'rewrite',classification:'safe',content:body('contract','The wrapper declares onIdle and clearQueue.'),evidence:[{index:0,quote:snapshot.entries[0].content},{index:1,quote:snapshot.entries[1].content}]};
      const requests=[];let mode='compatible';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);requests.push(req);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?mode:key.startsWith('relation_')?'unrelated':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
      }});
      const allowed=await judge.validate('memory',snapshot,[candidate],existing);
      const original=requests.splice(0);mode='contradicts';const refused=await judge.validate('memory',snapshot,[candidate],existing);
      const relations=original.filter(r=>r.questions.relation_0).map(r=>({state:(typeof r.state === "string" ? JSON.parse(r.state) : r.state),names:r.questions.relation_0.instructions.comparisonNames}));
      const support=original.find(r=>r.questions.supported_0);const counters=original.filter(r=>Object.keys(r.questions).some(k=>k.startsWith('counter_')));
      console.log(JSON.stringify({allowed:allowed.decision,refused:refused.decision,relations,original:existing,candidate,
        support:(typeof support.state === "string" ? JSON.parse(support.state) : support.state),counterStates:counters.map(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state)),review:allowed.candidateReview}));
    ''')
    assert value['allowed'] == 'allow' and value['refused'] == 'propose'
    assert value['relations'][0]['names'] == ['other.md']
    assert value['relations'][0]['state']['existingMemories'] == [value['original'][1]]
    # Factual source support sees the full new record, not its old reference.
    # Preservation and permission still review the exact predecessor below.
    assert 'existingMemories' not in value['support']
    assert 'mutationComparison' not in value['support']
    assert 'historicalMemoryOrigins' not in value['support']
    expected = {key: item for key, item in value['candidate'].items() if key != 'evidence'}
    expected.update(candidateIndex=0, originalCitationSources=[
        {'snapshotIndex': citation['index'], 'role': role,
         'quoteSha256': hashlib.sha256(citation['quote'].encode()).hexdigest()}
        for citation, role in zip(value['candidate']['evidence'], ['user', 'toolResult'], strict=True)
    ])
    assert value['support']['proposedMemoryOperations'] == [expected]
    assert [{key: item[key] for key in ('index', 'quote', 'role')}
            for item in value['support']['originalCitationsByCandidate']['0']] == [
        {**citation, 'role': role}
        for citation, role in zip(value['candidate']['evidence'], ['user', 'toolResult'], strict=True)
    ]
    for state in value['counterStates']:
        assert state['existingMemories'] == [value['original'][0]]
        assert state['proposedMemoryOperations'] == [expected]
    assert value['review']['complete']


def test_deletion_has_preservation_checks_without_a_novelty_question() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Delete obsolete.md; its claim is wrong.'}]};
      const old={name:'obsolete.md',classification:'safe',content:'---\nname: obsolete\ndescription: Wrong claim\ntype: project\n---\nWrong claim.'};
      const candidate={name:'obsolete.md',kind:'delete',classification:'safe',evidence:[{index:0,quote:snapshot.entries[0].content}]};
      const keys=[];let preservation=false;
      const result=await createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);keys.push(...Object.keys(req.questions));const state=(typeof req.state === "string" ? JSON.parse(req.state) : req.state);
        if(req.questions.counter_0_0)preservation=state.existingMemories[0].content===old.content && state.proposedMemoryOperations[0].kind==='delete';
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?'contradicts':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];}));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
      }}).validate('memory',snapshot,[candidate],[old]);
      console.log(JSON.stringify({keys,preservation,decision:result.decision}));
    ''')
    assert not any(key.startswith('relation_') for key in value['keys'])
    assert 'supported_0' in value['keys'] and 'counter_0_0' in value['keys']
    assert value['preservation'] and value['decision'] == 'propose'
