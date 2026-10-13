from support import isolated_run_bun


def test_internal_consistency_splits_from_source_support_without_losing_source_review() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'toolResult',content:'Observed contract. '+'s'.repeat(25000)}];
      const candidate={name:'contract.md',kind:'project',classification:'safe',content:'Contract explanation. '+'b'.repeat(25000),evidence:[{index:0,role:'toolResult',quote:'Observed contract.'}]};
      let requests=[];const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'offline',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')||key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'unrelated':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }))}));
      }});
      const result=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[]);
      const coherence=requests.find(r=>Object.keys(r.questions).length===1&&r.questions.coherence_0);
      const support=requests.find(r=>r.questions.supported_0),counter=requests.find(r=>r.questions.counter_0_0);
      console.log(JSON.stringify({decision:result.decision,coherenceOnly:!!coherence&&!coherence.state.frozenEvidence&&!coherence.state.supportEvidence,completeBody:coherence?.questions.coherence_0.instructions.candidate.content===candidate.content,completeSupport:support?.state.frozenEvidence.entries[0].entry.content===entries[0].content,completeCounter:counter?.state.reviewEvidence.entries[0].entry.content===entries[0].content,maxBytes:Math.max(...requests.map(r=>Buffer.byteLength(JSON.stringify(r))))}));
    ''')
    assert value['decision'] == 'allow'
    assert value['coherenceOnly'] and value['completeBody']
    assert value['completeSupport'] and value['completeCounter']
    assert value['maxBytes'] <= 64_000


def test_rewrite_consistency_transport_keeps_its_exact_bound_body() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'toolResult',content:'Observed contract. '+'s'.repeat(25000)}];
      const candidate={name:'contract.md',kind:'rewrite',classification:'safe',content:'Contract explanation. '+'b'.repeat(25000),evidence:[{index:0,role:'toolResult',quote:'Observed contract.'}]};
      let requests=[];const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'offline',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')||key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'unrelated':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }))}));
      }});
      const result=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[{name:'contract.md',kind:'project',classification:'safe',content:'Previous complete contract.'}]);
      const coherence=requests.find(r=>r.questions.coherence_0);
      const support=requests.find(r=>r.questions.supported_0),counter=requests.find(r=>r.questions.counter_0_0);
      console.log(JSON.stringify({decision:result.decision,coherenceOnly:!!coherence&&!coherence.state.frozenEvidence&&!coherence.state.supportEvidence,completeBody:coherence?.questions.coherence_0.instructions.candidate.contentReference.candidateIndex===0&&coherence?.state.proposedMemoryOperations[0].content===candidate.content,completeSupport:support?.state.frozenEvidence.entries[0].entry.content===entries[0].content,completeCounter:counter?.state.reviewEvidence.entries[0].entry.content===entries[0].content,maxBytes:Math.max(...requests.map(r=>Buffer.byteLength(JSON.stringify(r))))}));
    ''')
    assert value['decision'] == 'allow'
    assert value['completeBody']
    assert value['completeSupport'] and value['completeCounter']
    assert value['maxBytes'] <= 64_000


def test_complete_review_packs_preferred_windows_with_actual_wire_preflight() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'user',content:'The project uses SQLite.'},...Array.from({length:17},(_,i)=>({role:'toolResult',content:'Source '+i+': '+'x'.repeat(19000)})),{role:'user',content:'Correction: use PostgreSQL.'}];
      const candidate={kind:'project',name:'db.md',classification:'safe',content:'The project uses SQLite.',evidence:[{index:0,quote:entries[0].content}]};
      let calls=[],conflict=false;
      const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'offline',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);calls.push(r);const s=typeof r.state==='string'?JSON.parse(r.state):r.state;
        const answers=Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{
          const choice=k.startsWith('counter_')?(conflict&&s.reviewEvidence.entries.some(e=>e.index===18)?'contradicts':'compatible'):k.startsWith('relation_')?'unrelated':k.startsWith('coherence_')?'compatible':'grounded';
          return [k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===choice?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers}));
      }});
      const good=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[]);
      const coverage=[...new Set(calls.flatMap(r=>(typeof r.state==='string'?JSON.parse(r.state):r.state).reviewEvidence?.entries.map(e=>e.index)??[]))].sort((a,b)=>a-b);
      const maxBytes=Math.max(0,...calls.map(r=>Buffer.byteLength(JSON.stringify(r))));
      const noDuplicateContext=calls.every(r=>{const s=typeof r.state==='string'?JSON.parse(r.state):r.state;return !s.reviewEvidence||!s.supportEvidence.entries.some(e=>s.reviewEvidence.entries.some(other=>other.index===e.index))});
      conflict=true;calls=[];const held=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[]);
      console.log(JSON.stringify({good,held,coverage,maxBytes,noDuplicateContext}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['good']['telemetry']['evidenceWindows'] <= 16
    assert result['coverage'] == list(range(19))
    assert result['maxBytes'] <= 64_000
    assert result['noDuplicateContext']
    assert result['held']['decision'] == 'propose'
    assert result['held']['telemetry']['dimension'] == 'counterevidence'


def test_duplicate_support_quotes_use_exact_same_state_references_only() -> None:
    result = isolated_run_bun(r'''
      import {compactMemorySupportCitations} from './packages/continual-learning/extensions/jev-memory-predecessors.ts';
      import {createHash} from 'node:crypto';
      const quote='quoted source 😀 '.repeat(80),entry={index:7,entry:{message:{role:'toolResult',content:[{type:'text',text:'prefix '+quote+' suffix'}]}}};
      const state={frozenEvidence:{entries:[entry]},originalCitationsByCandidate:{0:[{index:7,role:'toolResult',quote}],1:[{index:8,role:'toolResult',quote}],2:[{index:7,role:'user',quote}],3:[{index:7,role:'toolResult',quote:'short'}]}};
      const before=JSON.stringify(state),result=compactMemorySupportCitations(state),c=result.originalCitationsByCandidate[0][0],ref=c.quoteReference;
      let text=result;for(const k of ref.statePath)text=text[k];const restored=text.slice(ref.start,ref.end);
      console.log(JSON.stringify({sourceUnchanged:before===JSON.stringify(state),exact:restored===quote,hash:createHash('sha256').update(restored).digest('hex')===ref.sha256,units:ref.units,unmatched:result.originalCitationsByCandidate[1][0].quote===quote,wrongRole:result.originalCitationsByCandidate[2][0].quote===quote,short:result.originalCitationsByCandidate[3][0].quote==='short',smaller:Buffer.byteLength(JSON.stringify(result))<Buffer.byteLength(before)}));
    ''')
    assert all(result[key] for key in ['sourceUnchanged', 'exact', 'hash', 'unmatched', 'wrongRole', 'short', 'smaller'])
    assert result['units'] == 'UTF-16'


def test_normal_project_review_has_no_artificial_request_byte_cap() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'user',content:'Keep the observed contract.'},{role:'toolResult',content:'Complete observation: '+'x'.repeat(70000)},{role:'user',content:'Final revocation: remove the contract.'}];
      const candidate={name:'contract.md',kind:'project',classification:'safe',content:'Keep the observed contract.',evidence:[{index:0,quote:entries[0].content}]};
      let requests=[];const judge=createJevJudge({enabled:true,apiKey:'offline',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{
          const revoked=k.startsWith('counter_')&&r.state.reviewEvidence.entries.some(e=>e.index===2);
          const choice=k.startsWith('counter_')?(revoked?'contradicts':'compatible'):k.startsWith('coherence_')?'compatible':k.startsWith('relation_')?'unrelated':'grounded';
          return [k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===choice?1:0]))}];
        }))}));
      }});
      const result=await judge.validate('memory',{contextEnabled:true,entries},[candidate],[]);
      console.log(JSON.stringify({result,maxBytes:Math.max(0,...requests.map(r=>Buffer.byteLength(JSON.stringify(r)))),complete:requests.some(r=>r.state.reviewEvidence?.entries.some(e=>e.entry.content===entries[1].content))}));
    ''')
    assert value['maxBytes'] > 64_000 and value['complete']
    assert value['result']['decision'] == 'propose'
    assert value['result']['telemetry']['dimension'] == 'counterevidence'


def test_explicit_historical_bound_keeps_relation_and_subset_window_checklists() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {partitionReviewedNewMemory} from './packages/continual-learning/extensions/independent-memory-partition.ts';
      const quote='Use pnpm.';
      const evidence={contextEnabled:true,entries:[{role:'user',content:quote},...Array.from({length:17},(_,i)=>({role:'toolResult',content:String(i)+'x'.repeat(19000)}))]};
      const candidates=[0,1].map(i=>({name:`fact-${i}.md`,kind:'project',classification:'safe',content:`---\nname: fact-${i}\ndescription: ${quote}\ntype: project\n---\n${quote}`,evidence:[{index:0,quote,role:'user'}]}));
      const judge=createJevJudge({maxRequestBytes:64000,enabled:true,apiKey:'offline',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{const label=k==='relation'?'independent':k.startsWith('supported')?'grounded':'compatible';return[k,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(c=>[c,c===label?1:0]))}]}))}));
      }});
      const source=await judge.validate('memory',evidence,candidates,[]);
      const relations=await judge.reviewMemoryRelations(evidence,candidates,[],source.candidateReview);
      const partition=partitionReviewedNewMemory(evidence,candidates,[],source.candidateReview,relations.review);
      const finalWindows=source.candidateReview.counterWindows;
      const corrupt=[finalWindows.slice(1),[...finalWindows,finalWindows[0]],[[999],...finalWindows],finalWindows.slice().reverse(),[[],...finalWindows],[[0.5],...finalWindows]];
      const refused=corrupt.every(counterWindows=>partitionReviewedNewMemory(evidence,candidates,[],{...source.candidateReview,counterWindows},relations.review).eligible.length===0);
      console.log(JSON.stringify({windows:source.telemetry.evidenceWindows,source:source.decision,relations:relations.telemetry.reason,partition,refused}));
    ''')
    assert value['windows'] == 16 and value['source'] == 'allow'
    assert value['relations'] == 'supported'
    assert value['partition']['eligible'] == [0, 1]
    assert value['partition']['writeAuthorized'] is False
    assert value['refused']


def test_normal_project_preserves_preferred_evidence_windows_without_a_byte_cap() -> None:
    value = isolated_run_bun(r'''
      import {citedMemoryEvidence} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'user',content:'Keep this contract.'},...Array.from({length:4},(_,i)=>({role:'toolResult',content:String(i)+'x'.repeat(19000)})),{role:'user',content:'Revoke this contract.'}];
      const candidate={name:'contract.md',kind:'project',classification:'safe',content:'Keep this contract.',evidence:[{index:0,quote:entries[0].content}]};
      const prepared=citedMemoryEvidence({contextEnabled:true,entries},[candidate]);
      console.log(JSON.stringify({windows:prepared.windows.length,coverage:prepared.windows.flatMap(w=>w.entries.map(e=>e.index))}));
    ''')
    assert value['windows'] > 1
    assert value['coverage'] == list(range(6))


def test_retention_questions_keep_complete_bodies_without_duplicate_corpus_state() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const existing=[0,1].map(i=>({name:`fact-${i}.md`,classification:'safe',type:'project',description:`Contract ${i}`,content:`Contract ${i}. `+'x'.repeat(10000)}));
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Review current contracts.'},{role:'toolResult',content:'Current source. '+'y'.repeat(19000)}]};
      let requests=[];const judge=createJevJudge({enabled:true,apiKey:'offline',fetch:async(_u,init)=>{const r=JSON.parse(init.body);requests.push(r);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([k,q])=>[k,{type:'choice',choice:'compatible',confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(c=>[c,c==='compatible'?1:0]))}]))}));}});
      const result=await judge.validate('memory',evidence,[],existing);
      const counters=requests.filter(r=>Object.keys(r.questions).some(k=>k.startsWith('counter_')));
      const complete=counters.every(r=>[0,1].every(i=>r.questions[`counter_${i}_${Object.keys(r.questions).find(k=>k.startsWith('counter_')).split('_').at(-1)}`].instructions.candidate.content===existing[i].content));
      console.log(JSON.stringify({decision:result.decision,noDuplicateCorpus:counters.every(r=>!r.state.existingMemories),complete,covered:result.telemetry.coveredEntries}));
    ''')
    assert value['noDuplicateCorpus'] and value['complete']
    assert value['decision'] == 'allow' and value['covered'] == 2
