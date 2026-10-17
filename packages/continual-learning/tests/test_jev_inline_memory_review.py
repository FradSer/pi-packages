from support import isolated_run_bun


def test_normal_project_reviews_keep_complete_actual_memory_values_inline():
    # Given V32's exact rewrite and complete original source/history,
    # When a normal project has no wire-byte cap, Then the judgment sees exact
    # bodies and source quotes without resolving transport pointers. This is a
    # wire contract proof only; controlled answers never establish truth/benefit.
    out = isolated_run_bun(r'''
      import fs from 'node:fs';import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-mutation-references.json','utf8'));
      const before=JSON.stringify(input),runs=[];
      for(const bounded of [false,true]){
        let requests=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,...(bounded?{maxRequestBytes:64_000}:{}),fetch:async(_u,init)=>{
          const text=String(init.body),r=JSON.parse(text);requests.push({hash:createHash('sha256').update(text).digest('hex'),payload:r});
          const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
            const labels=Object.keys(q.criteria),label=['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0];
            return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===label)]))}];
          }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
        }});
        const result=await judge.validate('memory',input.evidence,input.candidates,input.existing,undefined,undefined,undefined,input.memorySources);
        const states=requests.map(r=>({...r,state:typeof r.payload.state==='string'?JSON.parse(r.payload.state):r.payload.state}));
        const first=states.find(r=>Object.hasOwn(r.payload.questions,'counter_0_0'));
        const support=states.find(r=>Object.hasOwn(r.payload.questions,'supported_0'));
        runs.push({bounded,complete:result.candidateReview?.complete,counterHash:first.hash,
          supportHasPredecessors:Object.hasOwn(support.state,'existingMemories'),
          supportHasPreservation:Object.hasOwn(support.state,'mutationComparison'),
          supportSource:support.state.sourceComparisonEvidence,
          supportCompleteProposal:support.state.proposedMemoryOperations?.[0]?.content,
          body:first.payload.questions.counter_0_0.instructions.candidate,
          predecessor:first.state.existingMemories[0],
          textComparisons:states.filter(r=>r.state.reviewEvidence).map(r=>r.state.mutationComparison?.exactTextComparisons),
          expectedBody:input.candidates[0].content.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/,''),completeProposal:first.state.proposedMemoryOperations[0].content,expectedCompleteProposal:input.candidates[0].content,expectedPredecessor:input.existing[0].content,
          coverage:states.flatMap(r=>r.state.reviewEvidence?.entries.map(e=>e.index)??[]),
          pointers:states.flatMap(r=>Object.values(r.payload.questions).filter(q=>q.instructions.candidate?.contentReference)).length,
          questionReferences:states.flatMap(r=>Object.values(r.payload.questions).filter(q=>q.instructions.question.includes('quoteReference')||q.instructions.question.includes('UTF-16'))).length});
      }
      console.log(JSON.stringify({runs,unchanged:before===JSON.stringify(input),historical:input.historicalCounterWireHash}));
    ''')
    normal, bounded = out['runs']
    assert out['unchanged']
    assert normal['complete'] and bounded['complete']
    assert normal['coverage'] == bounded['coverage']
    assert normal['body'].get('content') == normal['expectedBody']
    assert normal['completeProposal'] == normal['expectedCompleteProposal']
    assert not normal['supportHasPredecessors'] and not normal['supportHasPreservation']
    assert normal['supportCompleteProposal'] == normal['expectedCompleteProposal']
    assert normal['supportSource']['entries'], 'source support lacks the complete bound current source'
    assert bounded['supportHasPredecessors'] and bounded['supportHasPreservation']
    assert normal['predecessor'].get('content') == normal['expectedPredecessor']
    assert normal['pointers'] == 0 and normal['questionReferences'] == 0
    assert all(normal['textComparisons']), 'rewrite windows lack exact predecessor/replacement text differences'
    assert all(item['writeAuthorized'] is False and item['observations'][0]['candidateIndex'] == 0 for item in normal['textComparisons'])
    assert not any(bounded['textComparisons'])
    assert bounded['body'].get('contentReference')
    assert bounded['predecessor'].get('contentReference')
    assert bounded['counterHash'] == out['historical']


def test_inline_values_do_not_relax_uncertainty_late_conflict_or_source_binding():
    out = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const original=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-mutation-references.json','utf8')),results=[];
      for(const mode of ['positive','uncertain','tail-conflict','changed-source','source-uncertain']){
        const input=structuredClone(original);let calls=0,seen=[];
        if(mode==='changed-source')input.evidence.entries.push({role:'user',content:'Final instruction revokes permission to change this record.'});
        const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,fetch:async(_u,init)=>{
          calls++;const r=JSON.parse(init.body),state=typeof r.state==='string'?JSON.parse(r.state):r.state;
          seen.push(...(state.reviewEvidence?.entries.map(e=>e.index)??[]));
          const tail=state.reviewEvidence?.entries.some(e=>e.index===original.evidence.entries.length-1);
          return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
            const labels=Object.keys(q.criteria);let choice=['compatible','grounded','consistent','independent','unrelated'].find(x=>labels.includes(x))??labels[0];
            const counter=key.startsWith('counter_');
            if(counter&&tail&&mode==='tail-conflict')choice='contradicts';
            const weak=counter&&mode==='uncertain'||key.startsWith('supported_')&&mode==='source-uncertain';
            return [key,{type:'choice',choice,confidence:weak?0.79:1,probabilities:Object.fromEntries(labels.map(k=>[k,k===choice?(weak?0.89:1):(weak?0.11/(labels.length-1):0)]))}];
          }))}));
        }});
        const result=await judge.validate('memory',input.evidence,input.candidates,input.existing,undefined,undefined,undefined,input.memorySources);
        results.push({mode,calls,seen,decision:result.decision,reason:result.telemetry.reason,complete:result.candidateReview?.complete});
      }
      console.log(JSON.stringify(results));
    ''')
    positive, uncertain, conflict, changed, source_uncertain = out
    assert positive['decision'] == 'allow' and positive['complete']
    assert uncertain['decision'] == 'propose'
    assert conflict['decision'] == 'propose'
    assert conflict['seen'] == positive['seen']
    assert changed['decision'] == 'propose' and changed['calls'] == 0
    assert changed['reason'] == 'invalid-response'
    assert source_uncertain['decision'] == 'propose'
    assert source_uncertain['seen'] == positive['seen']


def test_exact_rewrite_text_comparison_preserves_duplicates_order_warnings_and_line_endings():
    # Given an actual old/new record pair, When text comparison is attached,
    # Then exact missing occurrences are visible but semantic approval stays separate.
    value = isolated_run_bun(r'''
      import {memoryRewriteTextComparisons} from './packages/continual-learning/extensions/jev-memory-predecessors.ts';
      const existing=[{name:'record.md',content:'same\r\nrepeat\nrepeat\n古い条件\n'}];
      const operations=[{candidateIndex:4,name:'record.md',kind:'rewrite',content:'same\nrepeat\n新しい条件\n'}];
      const before=JSON.stringify({existing,operations});
      const compared=memoryRewriteTextComparisons(existing,operations);
      const reorder=memoryRewriteTextComparisons([{name:'record.md',content:'A\nB\n'}],[{candidateIndex:0,name:'record.md',kind:'rewrite',content:'B\nA\n'}]);
      const ignored=memoryRewriteTextComparisons(existing,[{candidateIndex:1,name:'record.md',kind:'delete',preservedIn:['other.md']},{candidateIndex:2,name:'other.md',kind:'create',content:'anything'}]);
      const ambiguous=memoryRewriteTextComparisons([...existing,{...existing[0],name:'RECORD.md'}],operations);
      console.log(JSON.stringify({compared,reorder,ignored,ambiguous,unchanged:before===JSON.stringify({existing,operations})}));
    ''')
    observation = value['compared']['observations'][0]
    assert value['unchanged'] and value['compared']['writeAuthorized'] is False
    assert observation['candidateIndex'] == 4
    assert observation['unmatchedPredecessorLines'] == [
        {'line': 1, 'text': 'same\r\n'}, {'line': 3, 'text': 'repeat\n'}, {'line': 4, 'text': '古い条件\n'},
    ]
    assert observation['unmatchedReplacementLines'] == [
        {'line': 1, 'text': 'same\n'}, {'line': 3, 'text': '新しい条件\n'},
    ]
    assert observation['equalLineOccurrences'] == 1
    reordered = value['reorder']['observations'][0]
    assert reordered['unmatchedPredecessorLines'] == reordered['unmatchedReplacementLines'] == []
    assert 'order' in value['reorder']['meaning'] and 'semantic preservation' in value['reorder']['meaning']
    assert value.get('ignored') is None and value.get('ambiguous') is None
