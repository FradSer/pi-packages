import pytest

from support import isolated_run_bun


@pytest.mark.parametrize('native', [False, True])
def test_semantic_repair_receives_real_observed_source_order(native):
    # Given V50's complete original source and stale semantic repair,
    # When correcting knowledge, Then the worker receives the same validated
    # read chronology as the reviewer, without losing or approving any source.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {mock} from 'bun:test';
      import {createHash} from 'node:crypto';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-order.json').json();
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,f.original[k]]));
      const name=f.original.operations[0].name,before=JSON.stringify(f),native=__NATIVE__;
      const memorySources={evidenceDigest:digest(f.snapshot),entryDigests:f.sourceEntryIndexes.map(i=>digest(f.snapshot.entries[i]))};
      let prompt,calls=0,tools,server;
      if(native){
        const agent=process.env.PI_CODING_AGENT_DIR;
        server=Bun.serve({hostname:'127.0.0.1',port:0,fetch:async request=>{
          calls++;const wire=await request.json();tools=wire.tools;
          prompt=wire.messages.filter(m=>m.role==='user').at(-1).content;
          const chunk=(delta,finish_reason)=>'data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',model:'offline',choices:[{index:0,delta,finish_reason}]})+'\n\n';
          return new Response(chunk({role:'assistant',content:JSON.stringify(f.response)},null)+chunk({},'stop')+'data: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}});
        }});
        fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({providers:{fixture:{baseUrl:`http://127.0.0.1:${server.port}/v1`,api:'openai-completions',apiKey:'offline',models:[{id:'offline',name:'offline',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:4096,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
        fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({packages:[],extensions:[],skills:[],retry:{enabled:false}}));
        process.env.PI_OFFLINE='1';process.argv[1]=fs.realpathSync('./node_modules/@earendil-works/pi-coding-agent/dist/cli.js');process.execPath=Bun.which('node');
      }else{
        const kit=await import('./packages/kit/src/index.ts');
        mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{calls++;prompt=input.prompt;tools=input.tools;return{exitCode:0,cancelled:false,stderr:'',text:JSON.stringify(f.response)}}}));
      }
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {containsSensitiveMemoryMaterial}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {locatedMemoryEvidence}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      try{
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:f.original,selectedNames:[name],repairableNames:[name],repairableFields:{[name]:['body','description']},errors:['counter evidence held'],memorySources,...(native?{model:'fixture/offline'}:{}),semanticContext:{frozenEvidence:f.snapshot,existingMemories:f.existing}});
        if(Array.isArray(prompt))prompt=prompt.filter(x=>x.type==='text').map(x=>x.text).join('');
        const context=JSON.parse(prompt.split('\n').at(-1));
        console.log(JSON.stringify({calls,tools:tools?.length??0,order:context.sourceReadOrder,
          sourceUnchanged:JSON.stringify(context.semanticContext.frozenEvidence)===JSON.stringify(locatedMemoryEvidence(f.snapshot)),
          unchanged:JSON.stringify(f)===before,sensitive:containsSensitiveMemoryMaterial(JSON.stringify(f)),
          chronologyInstruction:prompt.includes('Existing Memory is a correction target, not authoritative source'),
          temporalInstruction:prompt.includes('Optional temporal clarification')&&prompt.includes('current as observed in this task')&&prompt.includes('Cite both actual source observations')&&prompt.includes('Do not infer dates, releases, versions')&&prompt.includes('History is not a loophole')&&prompt.includes('do not change an already correct body merely because a verdict is uncertain'),
          oldFailureRetained:result.plan?.operations[0].content.includes("'clearQueue'>;")&&!result.plan?.operations[0].content.includes("'clearQueue' | 'onIdle'>;"),
          piVersion:JSON.parse(fs.readFileSync('./node_modules/@earendil-works/pi-coding-agent/package.json','utf8')).version}));
      }finally{server?.stop(true)}
    '''.replace('__NATIVE__', str(native).lower()), timeout=45)
    assert value.get('order'), 'semantic repair lost validated source-read chronology'
    assert value['order']['writeAuthorized'] is False
    comparison = next(c for c in value['order']['comparisons'] if c['sourcePath'] == '/work/p-limit/index.d.ts')
    assert comparison['laterBoundRead'] == {'callIndex': 55, 'resultIndex': 56}
    assert comparison['earlierSuccessfulReads']
    assert all(r['resultIndex'] < 55 for r in comparison['earlierSuccessfulReads'])
    assert value['chronologyInstruction'] and value['sourceUnchanged'] and value['unchanged']
    assert value['temporalInstruction'], 'repair offers no source-bound current-versus-earlier clarification'
    assert value['oldFailureRetained'] and not value['sensitive']
    assert value['calls'] == 1 and value['tools'] == 0 and value['piVersion'] == '1.2.0'


@pytest.mark.parametrize('mode', ['foreign-evidence', 'foreign-entry', 'missing-run',
                                  'changed-snapshot', 'failed-audit', 'ambiguous-audit',
                                  'failed-earlier', 'ambiguous-earlier', 'different-earlier', 'unbound'])
def test_repair_source_order_rejects_invalid_bindings_and_excludes_invalid_prior_reads(mode):
    value = isolated_run_bun(r'''
      import {mock}from'bun:test';import{createHash}from'node:crypto';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-order.json').json();
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const mode='__MODE__',message=x=>x.message??x,name=f.original.operations[0].name;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,f.original[k]]));
      const originalSources={evidenceDigest:digest(f.snapshot),entryDigests:f.sourceEntryIndexes.map(i=>digest(f.snapshot.entries[i]))};
      const allCalls=f.snapshot.entries.flatMap((x,index)=>message(x).role==='assistant'?(message(x).content??[]).filter(b=>b.type==='toolCall').map(call=>({call,index})):[]);
      const priorIndex=f.snapshot.entries.findIndex((x,i)=>i<55&&message(x).role==='toolResult'&&message(x).toolName==='read'&&allCalls.some(({call})=>call.id===message(x).toolCallId&&call.arguments.path==='/work/p-limit/index.d.ts'));
      if(priorIndex<0)throw Error('Missing original earlier read');
      const priorCall=allCalls.find(({call})=>call.id===message(f.snapshot.entries[priorIndex]).toolCallId);
      if(mode==='missing-run')delete f.snapshot.runId;
      if(mode==='changed-snapshot')message(f.snapshot.entries[0]).content='Changed evidence';
      if(mode==='failed-audit')message(f.snapshot.entries[56]).isError=true;
      if(mode==='ambiguous-audit')message(f.snapshot.entries[55]).content.push(structuredClone(message(f.snapshot.entries[55]).content[0]));
      if(mode==='failed-earlier')message(f.snapshot.entries[priorIndex]).isError=true;
      if(mode==='ambiguous-earlier')message(f.snapshot.entries[priorCall.index]).content.push(structuredClone(priorCall.call));
      if(mode==='different-earlier')priorCall.call.arguments.path='/different/index.d.ts';
      const sources={evidenceDigest:digest(f.snapshot),entryDigests:f.sourceEntryIndexes.map(i=>digest(f.snapshot.entries[i]))};
      if(mode==='foreign-evidence')sources.evidenceDigest='a'.repeat(64);
      if(mode==='foreign-entry')sources.entryDigests[0]='a'.repeat(64);
      if(!['missing-run','changed-snapshot'].includes(mode))identity.snapshotDigest=createHash('sha256').update(JSON.stringify(f.snapshot,null,2)+'\n').digest('hex');
      let calls=0,context;
      const kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{calls++;context=JSON.parse(input.prompt.split('\n').at(-1));return{exitCode:0,cancelled:false,stderr:'',text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[]})}}}));
      const{repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const r=await repairIncrementalMemoryPlan({identity,rejectedPlan:{...f.original,...identity},selectedNames:[name],repairableNames:[name],repairableFields:{[name]:['body','description']},errors:['held'],...(mode==='unbound'?{}:{memorySources:mode==='changed-snapshot'?originalSources:sources}),semanticContext:{frozenEvidence:f.snapshot,existingMemories:f.existing}});
      console.log(JSON.stringify({calls,failureKind:r.failureKind,order:context?.sourceReadOrder,priorIndex,planPresent:!!r.plan}));
    '''.replace('__MODE__', mode))
    assert not value['planPresent']
    if mode in ('failed-earlier', 'ambiguous-earlier', 'different-earlier', 'unbound'):
        assert value['calls'] == 1
        assert all(r['resultIndex'] != value['priorIndex']
                   for c in value.get('order', {}).get('comparisons', []) for r in c['earlierSuccessfulReads'])
        if mode == 'unbound':
            assert not value.get('order')
    else:
        assert value['calls'] == 0 and value['failureKind'] == 'intent'


@pytest.mark.parametrize('mode', ['rewrite', 'predecessor-only', 'delete', 'new-project',
                                  'failed-earlier-read', 'ambiguous-earlier-read', 'other-earlier-path', 'old-quote', 'model-conflict'])
def test_real_rewrite_receives_bound_current_source_in_every_counter_window(mode):
    # Given the retained real V32 source correction (also missed in V36),
    # When reviewing a rewrite, Then early source windows can compare the full
    # successor observation. Controlled answers prove coverage, not acceptance.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-mutation-references.json','utf8'));
      if('__MODE__'==='predecessor-only')input.candidates[0].content=input.candidates[0].content.replaceAll('index.d.ts','the inspected declaration');
      if('__MODE__'==='delete')input.candidates=[{...input.candidates[0],kind:'delete',preservedIn:[]}].map(({content,...rest})=>rest);
      if('__MODE__'==='new-project'){input.candidates[0].kind='project';input.existing=[];}
      const oldCall=input.evidence.entries[4].message.content.find(x=>x.type==='toolCall'&&x.arguments?.path==='/work/p-limit/index.d.ts');
      if('__MODE__'==='failed-earlier-read')input.evidence.entries[5].message.isError=true;
      if('__MODE__'==='ambiguous-earlier-read')input.evidence.entries[4].message.content.push(structuredClone(oldCall));
      if('__MODE__'==='other-earlier-path')oldCall.arguments.path='/different/index.d.ts';
      if('__MODE__'==='old-quote'){
        const quote=input.candidates[0].evidence[0].quote.replace(" | 'onIdle'",'');
        input.candidates[0].evidence=[{index:5,quote,role:'toolResult'}];
        input.candidates[0].content=input.candidates[0].content.replaceAll(" | 'onIdle'",'');
      }
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      input.memorySources.evidenceDigest=digest(input.evidence);
      const before=JSON.stringify(input),requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,fetch:async(_u,init)=>{
        const r=JSON.parse(init.body),state=typeof r.state==='string'?JSON.parse(r.state):r.state;
        if(state.reviewEvidence)requests.push({state,questions:r.questions});
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const labels=Object.keys(q.criteria),choice='__MODE__'==='model-conflict'&&key.startsWith('counter_')?'contradicts':['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0];
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===choice)]))}];
        }))}));
      }});
      const result=await judge.validate('memory',input.evidence,input.candidates,input.existing,undefined,undefined,undefined,input.memorySources);
      const bound=new Set(input.memorySources.entryDigests);
      const expected=input.evidence.entries.flatMap((entry,index)=>bound.has(digest(entry))&&entry.message?.role==='toolResult'&&entry.message?.details?.sourcePath?.endsWith('/index.d.ts')?[{index,entry}]:[]);
      const hashes=rows=>rows?.map(({index,entry})=>({index,sha256:digest(entry)}));
      console.log(JSON.stringify({windows:requests.map(({state,questions})=>({context:hashes(state.sourceComparisonEvidence?.entries),order:state.sourceComparisonEvidence?.observedReadOrder,quoteFacts:state.sourceComparisonEvidence?.exactQuoteComparisons,calls:state.sourceComparisonEvidence?.citationToolCalls.map(x=>({callIndex:x.callIndex,resultIndex:x.resultIndex})),coverage:state.reviewEvidence.entries.map(x=>x.index),instructed:Object.values(questions).every(q=>q.instructions.question.includes('sourceComparisonEvidence'))})),expected:hashes(expected),decision:result.decision,entryCount:input.evidence.entries.length,unchanged:before===JSON.stringify(input),complete:result.candidateReview?.complete}));
    '''.replace('__MODE__', mode))
    assert value['expected'], 'real fixture must include the bound successor declaration'
    assert len(value['windows']) > 1
    coverage = []
    for window in value['windows']:
        assert window.get('context'), 'rewrite lost current-source comparison outside its window'
        assert window['context'] == value['expected']
        assert [call['resultIndex'] for call in window['calls']] == [row['index'] for row in value['expected']]
        assert all(call['callIndex'] < call['resultIndex'] for call in window['calls'])
        if mode in ('failed-earlier-read', 'ambiguous-earlier-read', 'other-earlier-path'):
            assert not window.get('order'), 'invalid or different-path reads must not acquire paired chronology'
        else:
            assert window.get('order'), 'read chronology must name the paired old and bound successor reads'
            assert window['order']['writeAuthorized'] is False
            assert window['order']['comparisons'] == [{
                'sourcePath': '/work/p-limit/index.d.ts',
                'earlierSuccessfulReads': [{'callIndex': 4, 'resultIndex': 5}],
                'laterBoundRead': {'callIndex': 76, 'resultIndex': 77},
            }]
        if mode in ('rewrite', 'predecessor-only', 'delete', 'old-quote', 'model-conflict'):
            facts = window.get('quoteFacts')
            assert facts, 'paired source review lacks parent-computed exact quote comparison'
            assert facts['writeAuthorized'] is False
            assert len(facts['observations']) == 1
            fact = facts['observations'][0]
            assert fact['candidateIndex'] == 0 and fact['sourcePath'] == '/work/p-limit/index.d.ts'
            old = mode == 'old-quote'
            assert fact['citedRead'] == ({'callIndex': 4, 'resultIndex': 5} if old else {'callIndex': 76, 'resultIndex': 77})
            assert fact['laterBoundRead'] == {'callIndex': 76, 'resultIndex': 77, 'containsExactQuote': not old}
            assert fact['earlierSuccessfulReads'] == [{'callIndex': 4, 'resultIndex': 5, 'containsExactQuote': old}]
            assert ("'clearQueue'>;" if old else "'clearQueue' | 'onIdle'>;") in fact['exactQuote']
        else:
            assert not window.get('quoteFacts'), 'unpaired or unrelated reads must not acquire quote comparisons'
        assert window['instructed']
        coverage.extend(window['coverage'])
    assert coverage == list(range(value['entryCount']))
    assert value['unchanged'] and value['complete']
    assert value['decision'] == ('propose' if mode == 'model-conflict' else 'allow')


def test_retention_windows_keep_bound_successor_source_and_final_revocation():
    # Given earlier source, a later parent-verified source audit and a revocation,
    # When retaining a record across windows, Then every window gets the exact
    # relevant successor as comparison context, and all original entries remain.
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const audit=(id,path,text)=>[{message:{role:'assistant',content:[{type:'toolCall',id,name:'learning_read',arguments:{path,offset:1,limit:200}}]}},
        {message:{role:'toolResult',toolName:'learning_read',toolCallId:id,isError:false,content:[{type:'text',text}],details:{sourcePath:path,sourceSha256:'a'.repeat(64),readOnlyMaintenanceAudit:true}}}];
      const relevant=audit('fresh','/project/runtime.ts','export const mode = "new";');
      const unrelated=audit('other','/project/other.ts','Unrelated source does not authorize a preference.');
      const entries=[{role:'toolResult',content:'Earlier runtime.ts: export const mode = "old"; '+'context '.repeat(4000)},
        ...relevant,...unrelated,{role:'user',content:'Final revocation: do not retain this as a lasting preference.'}];
      const evidence={contextEnabled:true,entries};
      const sources={evidenceDigest:digest(evidence),entryDigests:[...relevant,...unrelated].map(digest)};
      const existing=[{name:'runtime.md',classification:'safe',type:'project',description:'runtime.ts declared mode',content:'---\nname: runtime\ndescription: runtime.ts declares the new mode\ntype: project\n---\nIn runtime.ts the observed declaration is export const mode = "new";'}];
      let negative=false,requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);const state=typeof r.state==='string'?JSON.parse(r.state):r.state;
        const final=state.reviewEvidence?.entries.some(e=>e.index===entries.length-1);
        const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const label=negative&&final?'contradicts':'compatible';
          return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
        }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const accepted=await judge.validate('memory',evidence,[],existing,undefined,undefined,undefined,sources);
      const windows=requests.map(r=>({state:typeof r.state==='string'?JSON.parse(r.state):r.state,questions:r.questions})).filter(r=>r.state.reviewEvidence);
      negative=true;const held=await judge.validate('memory',evidence,[],existing,undefined,undefined,undefined,sources);
      const before=requests.length;const bad=await judge.validate('memory',evidence,[],existing,undefined,undefined,undefined,{...sources,evidenceDigest:'wrong'});
      console.log(JSON.stringify({windows,accepted,held,bad,badRequests:requests.length-before,relevantResult:relevant[1],entryCount:entries.length}));
    ''')
    assert len(value['windows']) >= 2
    coverage = []
    for window in value['windows']:
        state = window['state']
        context = state.get('sourceComparisonEvidence')
        assert context, 'retention lost the parent-verified successor outside the current window'
        assert context['entries'] == [{'index': 2, 'entry': value['relevantResult']}]
        assert context['citationToolCalls'][0]['resultIndex'] == 2
        assert context['citationToolCalls'][0]['callIndex'] == 1
        assert state['supportEvidence']['entries'] == []  # No invented support citation.
        assert all('sourceComparisonEvidence' in q['instructions']['question'] for q in window['questions'].values())
        coverage.extend(e['index'] for e in state['reviewEvidence']['entries'])
    assert coverage == list(range(value['entryCount']))
    assert value['accepted']['candidateReview']['complete']
    assert value['held']['decision'] == 'propose'
    assert value['bad']['decision'] == 'propose'
    assert value['bad']['telemetry']['reason'] == 'invalid-response'
    assert value['badRequests'] == 0


def test_audit_labels_alone_and_unpaired_or_changed_context_do_not_supply_source_authority():
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const call={message:{role:'assistant',content:[{type:'toolCall',id:'r',name:'learning_read',arguments:{path:'/project/runtime.ts'}}]}};
      const result={message:{role:'toolResult',toolName:'learning_read',toolCallId:'r',isError:false,content:[{type:'text',text:'Actual source'}],details:{sourcePath:'/project/runtime.ts',sourceSha256:'a'.repeat(64),readOnlyMaintenanceAudit:true}}};
      const evidence={contextEnabled:true,entries:[call,result]};
      const existing=[{name:'runtime.md',classification:'safe',type:'project',description:'runtime.ts',content:'Observed runtime.ts source.'}];
      let requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);requests.push(r);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>[key,{type:'choice',choice:'compatible',confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k==='compatible'?1:0]))}]))}));
      }});
      await judge.validate('memory',evidence,[],existing);
      const unboundContexts=requests.map(r=>typeof r.state==='string'?JSON.parse(r.state):r.state).filter(s=>s.sourceComparisonEvidence);
      const rows=[];
      for(const kind of ['missing-call','changed-evidence','path-mismatch','failed-read']){
        const current=structuredClone(evidence);let bound=[call,result];
        if(kind==='missing-call')bound=[result];
        if(kind==='path-mismatch')current.entries[1].message.details.sourcePath='/project/other.ts';
        if(kind==='failed-read')current.entries[1].message.isError=true;
        const context={evidenceDigest:digest(kind==='changed-evidence'?evidence:current),entryDigests:(kind==='missing-call'?bound:current.entries).map(digest)};
        if(kind==='changed-evidence')current.entries.push({role:'user',content:'Later revocation'});
        const start=requests.length;const out=await judge.validate('memory',current,[],existing,undefined,undefined,undefined,context);rows.push({kind,out,calls:requests.length-start});
      }
      console.log(JSON.stringify({unboundContexts,rows}));
    ''')
    assert value['unboundContexts'] == []
    assert len(value['rows']) == 4
    for row in value['rows']:
        assert row['out']['decision'] == 'propose', row['kind']
        assert row['out']['telemetry']['reason'] == 'invalid-response', row['kind']
        assert row['calls'] == 0, row['kind']


def test_exact_source_quotes_are_candidate_scoped_and_cannot_override_a_semantic_hold():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-mutation-references.json','utf8'));
      const second=structuredClone(f.candidates[0]);second.name='second-contract.md';second.content=second.content.replaceAll(f.candidates[0].name,second.name);
      const predecessor=structuredClone(f.existing[0]);predecessor.name=second.name;predecessor.content=predecessor.content.replaceAll(f.existing[0].name,second.name);
      const candidates=[f.candidates[0],second],existing=[...f.existing,predecessor],contexts=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,fetch:async(_u,init)=>{
        const r=JSON.parse(init.body),s=typeof r.state==='string'?JSON.parse(r.state):r.state;
        if(s.reviewEvidence)contexts.push({reviewed:s.mutationComparison.reviewedCandidateIndexes,facts:s.sourceComparisonEvidence.exactQuoteComparisons});
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:0},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const labels=Object.keys(q.criteria),choice=/^counter(?:_description|_preservation)?_1_/.test(key)?'contradicts':['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0];
          return[key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===choice)]))}];
        }))}));
      }});
      const result=await judge.validate('memory',f.evidence,candidates,existing,undefined,undefined,undefined,f.memorySources);
      console.log(JSON.stringify({contexts,result}));
    ''')
    assert value['contexts']
    assert {tuple(c['reviewed']) for c in value['contexts']} == {(0,), (1,)}
    for context in value['contexts']:
        assert context['facts']['writeAuthorized'] is False
        assert [o['candidateIndex'] for o in context['facts']['observations']] == context['reviewed']
        assert all(o['laterBoundRead']['containsExactQuote'] for o in context['facts']['observations'])
    result = value['result']
    assert result['decision'] == 'propose' and result['candidateReview']['complete']
    assert [c['outcome'] for c in result['candidateReview']['candidates']] == ['passed', 'held']


def test_exact_source_quote_comparison_does_not_join_separate_text_blocks():
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import{createHash}from'node:crypto';
      import{createJevJudge}from'./packages/continual-learning/extensions/jev-learning.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-mutation-references.json','utf8'));
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex'),originalBound=new Set(f.memorySources.entryDigests);
      const boundIndexes=f.evidence.entries.flatMap((e,i)=>originalBound.has(digest(e))?[i]:[]),result=f.evidence.entries[77].message;
      const text=result.content[0].text,quote=f.candidates[0].evidence[0].quote,split=text.indexOf('\n',text.indexOf(quote));
      if(split<0)throw Error('Missing actual quote boundary');
      result.content=[{type:'text',text:text.slice(0,split)},{type:'text',text:text.slice(split+1)}];
      if(result.content.map(b=>b.text).join('\n')!==text)throw Error('Original source text changed');
      f.memorySources={evidenceDigest:digest(f.evidence),entryDigests:boundIndexes.map(i=>digest(f.evidence.entries[i]))};
      const contexts=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,fetch:async(_u,init)=>{
        const r=JSON.parse(init.body),s=typeof r.state==='string'?JSON.parse(r.state):r.state;if(s.reviewEvidence)contexts.push(s.sourceComparisonEvidence);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:0},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const labels=Object.keys(q.criteria),choice=['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0];return[key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===choice)]))}];
        }))}));
      }});const reviewed=await judge.validate('memory',f.evidence,f.candidates,f.existing,undefined,undefined,undefined,f.memorySources);
      console.log(JSON.stringify({contexts,complete:reviewed.candidateReview?.complete,blocks:result.content}));
    ''')
    assert value['complete'] and value['contexts']
    for context in value['contexts']:
        assert context['observedReadOrder']['comparisons']
        assert not context.get('exactQuoteComparisons')
        assert context['entries'][0]['entry']['message']['content'] == value['blocks']
