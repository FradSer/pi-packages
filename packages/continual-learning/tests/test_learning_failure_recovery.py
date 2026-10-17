from support import isolated_run_bun


def test_incremental_output_envelope_contains_exact_parent_identity() -> None:
    result = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const bindings={runId:'run-frozen',scopeKey:'scope"quoted',scopeDigest:'0'.repeat(64),artifactHash:'a'.repeat(64),snapshotDigest:'a'.repeat(64),dossierPath:'/tmp/dossier.json'};
      const prompt=buildIncrementalMemoryConsolidatorPrompt(bindings);
      const blocks=[...prompt.matchAll(/```json\n([\s\S]*?)\n```/g)].map(m=>m[1]);
      console.log(JSON.stringify({blocks,bindings}));
    ''')
    import json
    envelope = json.loads(result['blocks'][0])
    for key in ('runId', 'scopeKey', 'scopeDigest', 'artifactHash', 'snapshotDigest'):
        assert envelope[key] == result['bindings'][key]
    assert envelope['operations'] == []
    assert envelope['newMemories'] == []


def test_harness_counter_windows_check_revocation_without_repeating_authority() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:'Permanently forbid npm in this project.'},...Array.from({length:10},()=>({role:'toolResult',content:'unrelated '.repeat(500)})),{role:'assistant',content:'The source uses a FIFO queue.'}]};
      const candidates=[{op:'addRule',rule:{bash:'^npm(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Permanently forbid npm in this project.'}}];
      const requests=[];let mode='compatible';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['harness'],fetch:async(_url,init)=>{
        const req=JSON.parse(init.body);requests.push(req);
        const answers=Object.fromEntries(Object.entries(req.questions).map(([key,q])=>{
          const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?mode:key.startsWith('authority_')?'lasting':key.startsWith('family_')?'authorized':'faithful';
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const citations=[{index:0,eventIndex:0,source:'user',count:1,quote:snapshot.entries[0].content}];
      const good=await judge.validate('harness',snapshot,candidates,[],undefined,citations);
      const original=requests.splice(0);mode='contradicts';const revoked=await judge.validate('harness',snapshot,candidates,[],undefined,citations);
      mode='unclear';const uncertain=await judge.validate('harness',snapshot,candidates,[],undefined,citations);
      console.log(JSON.stringify({good,revoked,uncertain,questions:original.flatMap(r=>Object.entries(r.questions).filter(([k])=>/^counter_\d+_/.test(k)).map(([,q])=>q.instructions.question)),coverage:original.flatMap(r=>(typeof r.state === "string" ? JSON.parse(r.state) : r.state).reviewEvidence?.entries.map(e=>e.index)??[]),authority:original.some(r=>r.questions.authority_0&&r.questions.family_0)}));
    ''')
    assert result['good']['decision'] == 'allow'
    assert result['revoked']['decision'] == 'propose'
    assert result['uncertain']['decision'] == 'propose'
    assert result['coverage'] == list(range(12))
    assert result['authority'] is True
    assert all('lacks lasting authorization' not in question for question in result['questions'])
    assert all('missing repetition' in question for question in result['questions'])


def test_support_questions_keep_each_candidates_validated_citation_association() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quotes=['The test script is xo && ava && tsd.','The wrapper exposes clearQueue.'];
      const snapshot={contextEnabled:true,entries:quotes.map(content=>({role:'toolResult',content}))};
      const candidates=quotes.map((content,index)=>({name:`fact-${index}.md`,kind:'project',classification:'safe',content:`---\nname: fact-${index}\ndescription: ${content}\ntype: project\n---\n${content}`,evidence:[{index,quote:content}]}));
      let support;const counters=[];
      await createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{const req=JSON.parse(init.body);if(req.questions.supported_0)support=req;if(req.questions.counter_0_0)counters.push(req);const answers=Object.fromEntries(Object.entries(req.questions).map(([k,q])=>{const choice=k.startsWith('coherence_')?'compatible':k.startsWith('counter_')?'compatible':'grounded';return[k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===choice?1:0]))}];}));return new Response(JSON.stringify({model:'jev-1.13.0',answers}));}}).validate('memory',snapshot,candidates,[]);
      console.log(JSON.stringify({quotes,questions:support.questions,citations:support.state.originalCitationsByCandidate,counters,entries:(typeof support.state === "string" ? JSON.parse(support.state) : support.state).frozenEvidence.entries}));
    ''')
    for index, quote in enumerate(result['quotes']):
        for key in (f'supported_{index}', f'supported_description_{index}'):
            assert result['questions'][key]['instructions']['originalCitationsReference'] == f'originalCitationsByCandidate.{index}'
            citations = result['citations'][str(index)]
            assert citations == [{'index': index, 'quote': quote, 'role': 'toolResult'}]
    for index, quote in enumerate(result['quotes']):
        for key in (f'counter_{index}_0', f'counter_description_{index}_0'):
            assert result['counters'][0]['questions'][key]['instructions']['originalCitationIndexes'] == [index]
    assert len(result['entries']) == 2


def test_memory_planning_and_repair_distinguish_source_claims_from_verified_causes() -> None:
    # Given inspected source/comments and one successful run, When planning or
    # repairing knowledge, Then preserve configured behavior, not historical
    # counts or a comment's unverified explanation as an established cause.
    result = isolated_run_bun(r'''
      import {MEMORY_CITATION_GUIDANCE} from './packages/continual-learning/extensions/planner-prompts.ts';
      console.log(JSON.stringify({guidance:MEMORY_CITATION_GUIDANCE}));
    ''')
    guidance = result['guidance']
    assert 'Source comments establish what the source says' in guidance
    assert 'do not independently verify an external defect or its cause' in guidance
    assert 'successful test counts are historical observations' in guidance.lower()
    assert 'configured command or observed conditional behavior' in guidance


def test_memory_guidance_separates_task_commands_from_reusable_source_contracts() -> None:
    result = isolated_run_bun(r'''
      import {MEMORY_CITATION_GUIDANCE} from './packages/continual-learning/extensions/planner-prompts.ts';
      console.log(JSON.stringify({guidance:MEMORY_CITATION_GUIDANCE}));
    ''')
    assert 'task-local verification instruction' in result['guidance']
    assert 'reusable source behavior and public contracts' in result['guidance']
    assert 'observed configuration fact without inventing a standing workflow' in result['guidance']


def test_default_review_deadline_accepts_delayed_complete_response_without_relaxing_gates() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const evidence={contextEnabled:true,entries:[{role:'toolResult',content:'The wrapper exposes clearQueue.'}]};
      const candidates=[{name:'wrapper.md',kind:'project',classification:'safe',content:'The wrapper exposes clearQueue.',evidence:[{index:0,quote:'The wrapper exposes clearQueue.'}]}];
      const fetch=async(_url,init)=>{
        await new Promise((resolve,reject)=>{const timer=setTimeout(resolve,6200);init.signal.addEventListener('abort',()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));},{once:true});});
        const req=JSON.parse(init.body),answers=Object.fromEntries(Object.entries(req.questions).map(([k,q])=>{const choice=k.startsWith('coherence_')?'compatible':k.startsWith('counter_')?'compatible':'grounded';return[k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===choice?1:0]))}];}));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      };
      const defaultResult=await createJevJudge({enabled:true,apiKey:'fixture',fetch}).validate('memory',evidence,candidates,[]);
      const shortResult=await createJevJudge({enabled:true,apiKey:'fixture',timeout:5,fetch}).validate('memory',evidence,candidates,[]);
      const controller=new AbortController();setTimeout(()=>controller.abort(),5);
      const cancelled=await createJevJudge({enabled:true,apiKey:'fixture',fetch}).validate('memory',evidence,candidates,[],controller.signal);
      console.log(JSON.stringify({defaultResult,shortResult,cancelled}));
    ''')
    assert result['defaultResult']['decision'] == 'allow'
    assert result['defaultResult']['telemetry']['completedRequests'] == 2
    assert result['shortResult']['decision'] == 'propose'
    assert result['shortResult']['telemetry']['reason'] == 'timeout'
    assert result['cancelled']['decision'] == 'propose'
    assert result['cancelled']['telemetry']['reason'] == 'cancelled'


def test_memory_prompt_keeps_permanent_gates_out_of_knowledge() -> None:
    from pathlib import Path
    package = Path(__file__).resolve().parents[1]
    template = (package / 'prompts/incremental-memory-consolidator.md').read_text()
    guidance = (package / 'extensions/planner-prompts.ts').read_text()
    assert 'This project verifies changes with pnpm test' not in template
    for text in (template, guidance):
        assert 'even when permanent' in text
        assert 'relabel' in text
    assert 'response style' in template and 'editor choices' in template


def test_original_backlog_evidence_uses_the_same_empty_index_route() -> None:
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'extensions/inject-memory.ts').read_text()
    assert 'learningInput?.source === "backlog-session"' in source[source.index('allowEmptyIndexRouting:'):][:250]


def test_semantic_repair_is_a_sparse_delta_without_erasing_or_rewriting_other_intents() -> None:
    result = isolated_run_bun(r'''
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]},b={...a,name:'b.md',content:'B'};
      const original={runId:'original',operations:[{name:'old.md',kind:'rewrite',classification:'safe',content:'old'}],newMemories:[a,b]};
      const delta={runId:'changed',operations:[],newMemories:[{...a,content:'correct A'}]};
      const merged=mergeSemanticMemoryRepairDelta(original,delta,['a.md']);
      const errors=[];
      for(const update of [ {...delta,newMemories:[{...b,content:'drift'}]}, {...delta,newMemories:[{...a,classification:'safe'}]}, {...delta,newMemories:[{...a,name:'new.md'}]}, {...delta,newMemories:[a,a]}, {...delta,operations:[{name:'old.md',kind:'delete',classification:'safe'}]} ]) {
        try {mergeSemanticMemoryRepairDelta(original,update,['a.md']);errors.push(false)}catch {errors.push(true)}
      }
      console.log(JSON.stringify({merged,original,errors}));
    ''')
    assert result['merged']['runId'] == 'changed'  # Identity must still fail its independent gate.
    assert result['merged']['newMemories'][0]['content'] == 'correct A'
    assert result['merged']['newMemories'][1] == result['original']['newMemories'][1]
    assert result['merged']['operations'] == result['original']['operations']
    assert all(result['errors'])


def test_real_sparse_repair_omitted_array_preserves_every_original_proposal() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const raw=fs.readFileSync('./packages/continual-learning/tests/fixtures/real-sparse-memory-repair.json','utf8');
      const {original,delta}=JSON.parse(raw);
      const merged=mergeSemanticMemoryRepairDelta(original,delta);
      const invalid=[null,{},''].map(newMemories=>{
        try {mergeSemanticMemoryRepairDelta(original,{...delta,newMemories});return false;}catch{return true;}
      });
      console.log(JSON.stringify({sensitive:containsSensitiveMemoryMaterial(raw),original,delta,merged,invalid}));
    ''')
    assert not result['sensitive']
    assert 'newMemories' not in result['delta']
    assert result['merged']['newMemories'] == result['original']['newMemories']
    assert {row['name']: row for row in result['merged']['operations']} == {row['name']: row for row in result['delta']['operations']}
    assert [row['name'] for row in result['merged']['operations']] == [row['name'] for row in result['original']['operations']]
    assert all(result['invalid'])


def test_semantic_worker_sparse_output_preserves_full_plan_and_private_response() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]},b={...a,name:'b.md',content:'B'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[a,b]};
      const delta={...original,newMemories:[{...a,content:'correct A'}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(delta),cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'sparse-response-'));
      try{
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['a unsupported'],selectedNames:[],repairableNames:['a.md'],outputDir:root,semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}});
        const file=path.join(root,'repair-response.json'),saved=JSON.parse(await fs.readFile(file,'utf8'));
        console.log(JSON.stringify({result,saved,mode:(await fs.stat(file)).mode&0o777,prompt}));
      }finally{await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert result['result']['outcome'] == 'repaired'
    assert [c['content'] for c in result['result']['plan']['newMemories']] == ['correct A', 'B']
    assert result['saved']['runId'] == 'r'
    assert result['saved']['sensitive'] is False
    assert result['mode'] == 0o600
    assert 'Omitted operations and newMemories are retained byte-for-byte' in result['prompt']
    assert 'asynchronous operation completes' in result['prompt']
    assert 'exact source identifiers and comparison operators' in result['prompt']
    assert 'exactly one source-backed claim' in result['prompt']


def test_repair_diagnostic_omits_json_escaped_sensitive_material() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let output;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]};
      const credential='s'+'k-'+ 'a'.repeat(40),bearer='Bearer\n'+'b'.repeat(32);
      const cases=[JSON.stringify({...original,unused:credential}).replace('sk-','\\u0073k-'),JSON.stringify({...original,nested:{content:bearer}}),JSON.stringify({...original,content:bearer}).slice(0,-1),JSON.stringify(original)];
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({exitCode:0,stderr:'',text:output,cancelled:false})}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'repair-sensitive-'));
      try{
        const results=[];
        for(output of cases){
          await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:[],selectedNames:[],outputDir:root});
          const saved=JSON.parse(await fs.readFile(path.join(root,'repair-response.json'),'utf8'));
          results.push({sensitive:saved.sensitive,retained:'output' in saved});
        }
        console.log(JSON.stringify(results));
      }finally{await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert result == [{'sensitive': True, 'retained': False}] * 3 + [{'sensitive': False, 'retained': True}]


def test_initial_source_learning_does_not_infer_completion_from_invocation() -> None:
    from pathlib import Path
    package = Path(__file__).resolve().parents[1]
    guidance = (package / 'extensions/planner-prompts.ts').read_text()
    assert 'Do not infer execution or completion timing from a call or assignment alone' in guidance
    assert 'distinguish scheduling, invocation and settlement' in guidance


def test_cited_support_keeps_unique_tool_call_provenance_without_assistant_claims() -> None:
    result = isolated_run_bun(r'''
      import {citedMemoryEvidence} from './packages/continual-learning/extensions/jev-learning.ts';
      const call={type:'toolCall',id:'read-one',name:'read',arguments:{path:'/project/package.json'}};
      const assistant={role:'assistant',content:[{type:'text',text:'Everything is verified forever.'},call]};
      const result={role:'toolResult',toolCallId:'read-one',toolName:'read',content:'The test script is xo && ava && tsd.'};
      const candidate={name:'script.md',kind:'project',classification:'safe',content:result.content,evidence:[{index:1,quote:result.content}]};
      const entries=[assistant,result];
      const good=citedMemoryEvidence({contextEnabled:true,entries},[candidate]);
      const ambiguous=citedMemoryEvidence({contextEnabled:true,entries:[{...assistant,content:[call,call]},result]},[candidate]);
      const wrongName=citedMemoryEvidence({contextEnabled:true,entries:[assistant,{...result,toolName:'bash'}]},[candidate]);
      const future=citedMemoryEvidence({contextEnabled:true,entries:[{},result,assistant]},[candidate]);
      console.log(JSON.stringify({good,ambiguous:ambiguous.support.citationToolCalls,wrongName:wrongName.support.citationToolCalls,future:future.support.citationToolCalls,entries,call}));
    ''')
    assert result['good']['support']['citationToolCalls'] == [{'resultIndex': 1, 'callIndex': 0, 'toolCall': result['call']}]
    assert all(not result[key] for key in ('ambiguous', 'wrongName', 'future'))
    assert [item['entry'] for window in result['good']['windows'] for item in window['entries']] == result['entries']


def test_harness_support_questions_keep_their_original_user_citation() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='Permanently forbid npm commands in this project.';
      const evidence={contextEnabled:true,entries:[{role:'user',content:'Run pnpm test for this task. '+quote},{role:'user',content:'Keep ordinary prose readable.'}]};
      const candidate={op:'addRule',rule:{bash:String.raw`^npm(?:[ \t]|$(?![\s\S]))`,action:'block',message:quote}};
      let support;
      await createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const r=JSON.parse(init.body);if(r.questions.authority_0)support=r;
        const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const choice=key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?'compatible':key.startsWith('authority_')?'lasting':key.startsWith('family_')?'authorized':'faithful';return[key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}];}));return new Response(JSON.stringify({model:'jev-1.13.0',answers}));
      }}).validate('harness',evidence,[candidate],[],undefined,[{index:0,eventIndex:0,source:'user',quote,count:1}]);
      console.log(JSON.stringify({questions:support.questions,quote}));
    ''')
    for key in ('authority_0', 'family_0'):
        assert result['questions'][key]['instructions']['originalCitations'] == [{'index': 0, 'quote': result['quote'], 'role': 'user'}]


def test_automatic_memory_distills_lessons_without_dropping_explicit_requests() -> None:
    from pathlib import Path
    template = (Path(__file__).resolve().parents[1] / 'prompts/incremental-memory-consolidator.md').read_text()
    assert 'Automatic Memory is distilled lessons, not a copy of the source inventory' in template
    assert 'non-obvious reusable contracts and pitfalls' in template
    assert 'Explicitly requested knowledge and personal preferences must not be dropped' in template


def test_semantic_repair_preserves_already_reviewed_memory_fields_and_their_citations() -> None:
    result = isolated_run_bun(r'''
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const a={name:'a.md',kind:'project',classification:'safe',content:'---\nname: original\ndescription: Reviewed description\ntype: project\n---\nReviewed body.\n',evidence:[{index:0,quote:'Original fact'}]};
      const original={operations:[],newMemories:[a]};
      const delta={operations:[],newMemories:[{...a,content:'---\nname: drift\ndescription: Replacement description\ntype: preference\n---\nReplacement body.\n',evidence:[{index:1,quote:'Additional fact'}]}]};
      const body=mergeSemanticMemoryRepairDelta(original,delta,['a.md'],{'a.md':['body']});
      const description=mergeSemanticMemoryRepairDelta(original,delta,['a.md'],{'a.md':['description']});
      const both=mergeSemanticMemoryRepairDelta(original,delta,['a.md'],{'a.md':['body','description']});
      let invalid=false;try{mergeSemanticMemoryRepairDelta(original,{...delta,newMemories:[{...a,content:'No header'}]},['a.md'],{'a.md':['body']})}catch{invalid=true}
      console.log(JSON.stringify({body,description,both,invalid}));
    ''')
    body = result['body']['newMemories'][0]
    description = result['description']['newMemories'][0]
    assert body['content'] == '---\nname: original\ndescription: Reviewed description\ntype: project\n---\nReplacement body.\n'
    assert description['content'] == '---\nname: original\ndescription: Replacement description\ntype: project\n---\nReviewed body.\n'
    assert result['both']['newMemories'][0]['content'] == '---\nname: original\ndescription: Replacement description\ntype: project\n---\nReplacement body.\n'
    assert body['evidence'] == description['evidence'] == [{'index':0,'quote':'Original fact'},{'index':1,'quote':'Additional fact'}]
    assert result['invalid']


def test_field_repair_uses_all_complete_review_holds_not_first_failure_diagnostics() -> None:
    result = isolated_run_bun(r'''
      import {semanticMemoryRepairFields} from './packages/continual-learning/extensions/inject-memory.ts';
      import {createHash} from 'node:crypto';
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const candidates=[{name:'a.md',content:'original'}];
      const review={complete:true,purpose:'diagnostic-only',candidatesDigest:digest(candidates),candidates:[{index:0,candidateDigest:digest(candidates[0]),heldChecks:['supported_0','supported_description_0','counter_description_0_1']}]};
      const both=semanticMemoryRepairFields(candidates,review);
      const description=semanticMemoryRepairFields(candidates,{...review,candidates:[{...review.candidates[0],heldChecks:['supported_description_0']}]});
      console.log(JSON.stringify({both,description,stale:semanticMemoryRepairFields([{name:'a.md',content:'changed'}],review)??null,incomplete:semanticMemoryRepairFields(candidates,{...review,complete:false})??null}));
    ''')
    assert result['both']=={'a.md':['body','description']}
    assert result['description']=={'a.md':['description']}
    assert result['stale'] is None and result['incomplete'] is None


def test_repair_uses_same_unique_bounded_plan_framing_as_initial_planner() -> None:
    result=isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let text;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({exitCode:0,stderr:'',text,cancelled:false})}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a'};
      const original={kind:'incremental-memory-plan',version:1,...identity,operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'safe',content:'Observed fact',evidence:[{index:0,quote:'Observed fact'}]}]};
      const input={identity,rejectedPlan:original,errors:[],selectedNames:[]};
      const outcomes=[];
      for(const value of ['Explanation of the repair.\n\n'+JSON.stringify(original),JSON.stringify(original)+'\n'+JSON.stringify(original),'Incomplete\n{"kind":"incremental-memory-plan"',JSON.stringify({...original,kind:'harness-consolidation-plan'})]){
        text=value;outcomes.push(await repairIncrementalMemoryPlan(input));
      }
      console.log(JSON.stringify(outcomes));
    ''')
    assert result[0]['outcome']=='repaired'
    assert result[0]['plan']['runId']=='r'
    assert all(row['outcome']=='failed' for row in result[1:])


def test_planning_and_repair_preserve_type_level_scope_in_index_claims() -> None:
    result=isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let repair;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{repair=input.prompt;return {exitCode:0,stderr:'',text:'{}',cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {buildIncrementalMemoryConsolidatorPrompt}=await import('./packages/continual-learning/extensions/planner-prompts.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a'};
      await repairIncrementalMemoryPlan({identity,rejectedPlan:{},errors:[],selectedNames:[]});
      console.log(JSON.stringify({repair,initial:buildIncrementalMemoryConsolidatorPrompt({...identity,dossierPath:'/tmp/dossier'})}));
    ''')
    for text in result.values():
        assert 'type-level restriction' in text
        assert 'one independently supported clause' in text


def test_citation_indentation_repair_preserves_exact_original_evidence() -> None:
    result = isolated_run_bun(r'''
      import {repairCitationIndentation,candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      const text='before\n\tNote: pending only.\n\n\tWhen enabled, reject.\nafter';
      const candidate={name:'a.md',content:'unchanged',evidence:[{index:0,quote:'Note: pending only.\n\nWhen enabled, reject.'}]};
      const plan={operations:[],newMemories:[candidate]};
      const evidence={entries:[{role:'toolResult',content:text}]};
      const fixed=repairCitationIndentation(plan,evidence);
      const bad=[{role:'assistant',content:text},{role:'toolResult',content:text+'\n'+text}];
      const unchanged=bad.map(entry=>repairCitationIndentation(plan,{entries:[entry]}));
      const invented=repairCitationIndentation({...plan,newMemories:[{...candidate,evidence:[{index:0,quote:'Note: pending only.\nWhen disabled, reject.'}]}]},evidence);
      console.log(JSON.stringify({plan,fixed,problems:candidateCitationProblems(evidence,fixed.plan.newMemories),unchanged,invented}));
    ''')
    assert result['fixed']['corrections'] == [{'field': 'newMemories', 'candidate': 0, 'citation': 0, 'index': 0}]
    assert result['fixed']['plan']['newMemories'][0]['evidence'][0]['quote'] == '\tNote: pending only.\n\n\tWhen enabled, reject.'
    assert result['fixed']['plan']['newMemories'][0]['content'] == 'unchanged'
    assert result['plan']['newMemories'][0]['evidence'][0]['quote'].startswith('Note:')
    assert result['problems'] == []
    assert all(not item['corrections'] for item in result['unchanged'])
    assert result['invented']['corrections'] == []


def test_structural_slot_restores_indentation_without_worker_or_gate_bypass() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:1,stderr:'blocked fixture',text:'',cancelled:false}}}));
      const {repairIncrementalMemoryPlan,candidateCitationProblems,memoryAttemptDiagnostic}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'citation-slot-'));
      try {
        const text='\tNote: pending only.\n\n\tWhen enabled, reject.';
        const rejectedPlan={operations:[],newMemories:[{name:'a.md',content:'unchanged',evidence:[{index:0,quote:'Note: pending only.\n\nWhen enabled, reject.'}]}]};
        const input={structuralCorrection:true,outputDir:root,identity:{runId:'r',snapshotDigest:'s'},selectedNames:[],errors:['newMemories[0].evidence[0].quote is not present in the cited snapshot entry'],rejectedPlan,semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:text}]},existingMemories:[]}};
        const repaired=await repairIncrementalMemoryPlan(input);
        const provenance=JSON.parse(await fs.readFile(path.join(root,'citation-indentation-repair.json'),'utf8'));
        const problems=candidateCitationProblems(input.semanticContext.frozenEvidence,repaired.plan.newMemories);
        const refused=await repairIncrementalMemoryPlan({...input,semanticContext:{...input.semanticContext,frozenEvidence:{entries:[{role:'assistant',content:text}]}}});
        console.log(JSON.stringify({repaired,provenance,problems,refused,calls,diagnostic:memoryAttemptDiagnostic({outcome:'rejected',stopReason:'untrusted ignored',structuralRejection:'citation'})}));
      }finally{await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert result['repaired']['outcome'] == 'repaired'
    assert result['repaired']['usage'] == {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'totalTokens': 0, 'cost': 0}
    assert result['problems'] == []
    assert result['provenance']['snapshotDigest'] == 's'
    assert result['provenance']['corrections'][0]['index'] == 0
    assert result['calls'] == 1
    assert result['refused']['outcome'] == 'failed'
    assert result['diagnostic'] == 'Memory citation validation rejected'


def test_mixed_citation_failure_supplies_exact_hint_without_rewriting_other_sources() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const rejectedPlan={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'a.md',kind:'project',classification:'safe',content:'fact',evidence:[{index:0,quote:'Note.\nWhen enabled.'},{index:1,quote:'test enabled'}]}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(rejectedPlan),cancelled:false}}}));
      const {repairIncrementalMemoryPlan,candidateCitationProblems}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const snapshot={entries:[{role:'toolResult',content:'\tNote.\n\tWhen enabled.'},{role:'toolResult',content:'199:test\n200: enabled'}]};
      const repaired=await repairIncrementalMemoryPlan({identity,rejectedPlan,selectedNames:[],structuralCorrection:true,errors:['Citations are invalid: quote is absent'],semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
      const payload=JSON.parse(prompt.slice(prompt.lastIndexOf('\n')+1));
      console.log(JSON.stringify({payload,rejectedPlan,remaining:candidateCitationProblems(snapshot,repaired.plan.newMemories)}));
    ''')
    assert result['payload']['rejectedPlan'] == result['rejectedPlan']
    assert result['payload']['citationSpellingHints'] == [{'field': 'newMemories', 'candidate': 0, 'citation': 0, 'index': 0, 'quote': '\tNote.\n\tWhen enabled.'}]
    assert any('cited entry 1' in error for error in result['remaining'])
