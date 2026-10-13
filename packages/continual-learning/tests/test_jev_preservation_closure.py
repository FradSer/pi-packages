from support import isolated_run_bun


def test_complete_mutation_review_bounds_each_question_to_its_preservation_dependencies() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const existing=Array.from({length:7},(_,i)=>({name:`record-${i}.md`,classification:'safe',type:'project',description:`Record ${i}`,content:`Old record ${i}. `+'old knowledge '.repeat(350)}));
      const entries=Array.from({length:7},(_,i)=>({role:'toolResult',content:`Observed source ${i}. `+'source '.repeat(500)}));entries.push({role:'user',content:'Correction: the replacement no longer preserves record zero.'});
      const candidates=existing.map((item,i)=>({name:item.name,kind:i===0?'delete':'rewrite',classification:'safe',...(i===0?{verdict:'SUBSUMED',preservedIn:['record-1.md']}:{content:`Replacement ${i}. `+'retained knowledge '.repeat(420)}),evidence:[{index:i,quote:`Observed source ${i}.`}]}));
      let conflict=false,requests=[];const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);const s=typeof r.state==='string'?JSON.parse(r.state):r.state;
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const answer=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?(conflict&&key.startsWith('counter_0_')&&s.reviewEvidence.entries.some(e=>e.index===7)?'contradicts':'compatible'):key.startsWith('relation_')?'supplement':'grounded';
          return [key,{type:'choice',choice:answer,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===answer?1:0]))}];
        }))}));
      }});
      const good=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);const calls=requests;
      let exact=true;const seenOld=new Set(),seenNew=new Set(),coverage=Array.from({length:7},()=>new Set());let deletionDependency=false;
      for(const r of calls){const s=typeof r.state==='string'?JSON.parse(r.state):r.state;
        for(const old of s.existingMemories??[]){exact&&=JSON.stringify(old)===JSON.stringify(existing.find(x=>x.name===old.name));seenOld.add(old.name)}
        for(const op of s.proposedMemoryOperations??[]){const {candidateIndex,originalCitationSources,...body}=op;const {evidence,...expected}=candidates[candidateIndex];exact&&=JSON.stringify(body)===JSON.stringify(expected);seenNew.add(op.name)}
        for(const key of Object.keys(r.questions)) {const match=/^counter_(\d+)_/.exec(key);if(match){const index=Number(match[1]);s.reviewEvidence.entries.forEach(e=>coverage[index].add(e.index));if(index===0){deletionDependency||=s.existingMemories.some(x=>x.name==='record-0.md')&&s.existingMemories.some(x=>x.name==='record-1.md')&&s.proposedMemoryOperations.some(x=>x.name==='record-1.md'&&x.content===candidates[1].content)}}}
      }
      conflict=true;requests=[];const bad=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);
      requests=[];const oversized=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing.map(item=>({...item,content:item.content+'old knowledge '.repeat(600)})));const oversizedCalls=requests.length;
      console.log(JSON.stringify({good,bad,oversized,oversizedCalls,requests:calls.length,maxBytes:Math.max(0,...calls.map(r=>Buffer.byteLength(JSON.stringify(r)))),exact,seenOld:[...seenOld].sort(),seenNew:[...seenNew].sort(),coverage:coverage.map(x=>[...x].sort()),deletionDependency}));
    ''')
    assert value['good']['decision'] == 'allow'
    assert value['requests'] > 0 and value['maxBytes'] <= 64_000
    assert value['exact'] and value['deletionDependency']
    assert value['seenOld'] == value['seenNew'] == [f'record-{i}.md' for i in range(7)]
    assert all(entries == list(range(8)) for entries in value['coverage'])
    assert value['bad']['decision'] == 'propose'
    assert value['bad']['telemetry']['dimension'] == 'counterevidence'

    assert value['oversized']['decision'] == 'propose'
    assert value['oversized']['telemetry']['reason'] == 'bounds'
    assert value['oversizedCalls'] == 0


def test_mixed_create_delete_keeps_unmodified_preservation_target_and_holds_private_input() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'user',content:'Archive the duplicate only if the retained note preserves the source. The project uses pnpm.'}];
      const existing=[{name:'duplicate.md',classification:'safe',type:'project',description:'duplicate',content:'Required retained fact.'},{name:'retained.md',classification:'safe',type:'project',description:'retained',content:'Required retained fact.'}];
      const candidates=[{name:'duplicate.md',kind:'delete',classification:'safe',verdict:'SUBSUMED',preservedIn:['retained.md'],evidence:[{index:0,quote:'Archive the duplicate only if the retained note preserves the source.'}]},{name:'pnpm.md',kind:'project',classification:'safe',content:'The project uses pnpm.',evidence:[{index:0,quote:'The project uses pnpm.'}]}];
      let calls=[];const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);calls.push(r);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const choice=key.startsWith('coherence_')||key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'supplement':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}]}))}));
      }});
      const good=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);let dependency=true,references=true;
      for(const r of calls){const s=typeof r.state==='string'?JSON.parse(r.state):r.state;
        for(const [key,q] of Object.entries(r.questions)){
          if(/^supported_0$|^counter_0_/.test(key)) dependency&&=existing.every(old=>s.existingMemories.some(x=>JSON.stringify(x)===JSON.stringify(old)));
          const ref=q.instructions.candidate?.contentReference;if(ref) references&&=s[ref.field].filter(x=>x.candidateIndex===ref.candidateIndex).length===1&&s[ref.field].find(x=>x.candidateIndex===ref.candidateIndex)[ref.property]===candidates[ref.candidateIndex].content;
        }
      }
      calls=[];const denied=await judge.validate('memory',{contextEnabled:true,entries},candidates,[...existing,{name:'private.md',classification:'private',type:'project',description:'Private context',content:'Unrelated private context.'}]);
      console.log(JSON.stringify({good,dependency,references,denied,deniedCalls:calls.length}));
    ''')
    assert value['good']['decision'] == 'allow'
    assert value['dependency'] and value['references']
    assert value['denied']['decision'] == 'propose'
    assert value['denied']['telemetry']['reason'] == 'private-memory-denied'
    assert value['deniedCalls'] == 0



def test_context_cannot_be_replaced_by_quotes_when_complete_counter_request_exceeds_bound() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=[{role:'toolResult',content:'The blue service is billing production. Billing uses OAuth. '+'context '.repeat(1200)},{role:'toolResult',content:'blue now uses legacy auth. '+'z'.repeat(44000)}];
      const candidates=[{name:'contract.md',kind:'rewrite',classification:'safe',content:'Billing uses OAuth. '+'retained '.repeat(750),evidence:[{index:0,quote:'Billing uses OAuth.'}]}];
      const existing=[{name:'contract.md',classification:'safe',type:'project',description:'contract',content:'Earlier contract. '+'old '.repeat(2000)}];
      let calls=0;const judge=createJevJudge({maxRequestBytes:64_000,enabled:true,apiKey:'fixture',fetch:async()=>{calls++;throw Error('No request may omit alias context')}});
      console.log(JSON.stringify({result:await judge.validate('memory',{contextEnabled:true,entries},candidates,existing),calls}));
    ''')
    assert value['result']['decision'] == 'propose'
    assert value['result']['telemetry']['reason'] == 'bounds'
    assert value['calls'] == 0


def test_normal_mutation_groups_keep_full_source_and_final_revocations() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=Array.from({length:7},(_,i)=>({role:'toolResult',content:`Observed source ${i}. `+'source context '.repeat(800)}));
      entries.push({role:'user',content:'Final revocation: record zero must retain the old condition.'});
      const existing=Array.from({length:7},(_,i)=>({name:`record-${i}.md`,classification:'safe',type:'project',description:`Record ${i}`,content:`Old record ${i}. `+'required knowledge '.repeat(100)}));
      const candidates=existing.map((item,i)=>({name:item.name,kind:i===0?'delete':'rewrite',classification:'safe',...(i===0?{verdict:'SUBSUMED',preservedIn:['record-1.md']}:{content:`Replacement ${i}. `+'retained knowledge '.repeat(100)}),evidence:[{index:i,quote:`Observed source ${i}.`}]}));
      let requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);const s=r.state;
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?(key.startsWith('counter_0_')&&s.reviewEvidence.entries.some(e=>e.index===7)?'contradicts':'compatible'):key.startsWith('relation_')?'supplement':'grounded';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }))}));
      }});
      const before=JSON.stringify({entries,existing,candidates});const result=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);
      const counters=requests.filter(r=>r.state.reviewEvidence), coverage=Array.from({length:7},()=>new Set());
      let exact=true,dependency=false;
      for(const r of counters){const s=r.state;
        for(const key of Object.keys(r.questions)){const m=/^counter_(\d+)_/.exec(key);if(!m)continue;const i=Number(m[1]);
          for(const entry of s.reviewEvidence.entries)coverage[i].add(entry.index);
          const cited=[...s.supportEvidence.entries,...s.reviewEvidence.entries].find(e=>e.index===i);
          exact&&=JSON.stringify(cited.entry)===JSON.stringify(entries[i]);
          if(i===0)dependency||=s.existingMemories.some(m=>m.name===existing[1].name&&m.content===existing[1].content)&&s.proposedMemoryOperations.some(m=>m.name===candidates[1].name&&m.content===candidates[1].content);
        }
      }
      console.log(JSON.stringify({result,requests:requests.length,maxCandidates:Math.max(...counters.map(r=>new Set(Object.keys(r.questions).map(k=>/^counter(?:_description)?_(\d+)_/.exec(k)?.[1])).size)),coverage:coverage.map(s=>[...s].sort()),exact,dependency,unchanged:before===JSON.stringify({entries,existing,candidates})}));
    ''')
    assert value['maxCandidates'] == 1
    assert value['requests'] <= 128
    assert value['exact'] and value['dependency'] and value['unchanged']
    assert all(indexes == list(range(8)) for indexes in value['coverage'])
    assert value['result']['decision'] == 'propose'
    assert value['result']['telemetry']['dimension'] == 'counterevidence'


def test_normal_mutation_total_budget_covers_the_complete_bounded_candidate_matrix() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const entries=Array.from({length:16},(_,i)=>({role:'toolResult',content:`Source ${i}. `+'x'.repeat(19000)}));
      const existing=Array.from({length:33},(_,i)=>({name:`record-${i}.md`,classification:'safe',type:'project',description:`Record ${i}`,content:`Old ${i}.`}));
      const candidates=existing.map((item,i)=>({kind:'rewrite',name:item.name,classification:'safe',content:`New ${i}.`,evidence:[{index:i%16,quote:`Source ${i%16}.`}]}));
      let calls=0;const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{calls++;const r=JSON.parse(init.body);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const choice=key.startsWith('coherence_')||key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'supplement':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}]}))}));}});
      const complete=await judge.validate('memory',{contextEnabled:true,entries},candidates.slice(0,32),existing.slice(0,32));const completeCalls=calls;calls=0;
      const oversized=await judge.validate('memory',{contextEnabled:true,entries},candidates,existing);
      console.log(JSON.stringify({complete,completeCalls,oversized,oversizedCalls:calls}));
    ''')
    assert value['complete']['decision'] == 'allow'
    assert value['completeCalls'] == 32 * (16 + 2)
    assert value['complete']['telemetry']['completedWindows'] == 16
    assert value['oversizedCalls'] == 0
    assert value['oversized']['decision'] == 'propose'
    assert value['oversized']['telemetry']['reason'] == 'bounds'
    assert value['oversized']['telemetry']['boundsKind'] == 'candidates'
    assert value['oversized']['telemetry']['boundsCount'] == 33
