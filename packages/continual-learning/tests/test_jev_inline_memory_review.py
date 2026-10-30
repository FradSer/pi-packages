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


def test_complete_source_observations_retain_the_original_questions_and_windows():
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const questions={};const judge=createJevJudge({enabled:true,apiKey:'controlled-fixture',allowPrivateMemory:true,independentMemoryApplication:true,requestConcurrency:1,fetch:async(_u,init)=>{
        const r=JSON.parse(String(init.body));Object.assign(questions,r.questions);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{
          const labels=Object.keys(q.criteria),positive=['compatible','grounded','unrelated'].find(x=>labels.includes(x))??labels[0];return [k,{type:'choice',choice:positive,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===positive)]))}];
        }))}));
      }});
      const evidence={schemaVersion:1,contextEnabled:true,entries:[{role:'user',content:'Keep the observed project callable interface.'}]},candidates=[{name:'interface.md',kind:'project',classification:'private',content:'---\nname: interface\ndescription: Observed project callable interface\ntype: project\n---\nThe user identified a project callable interface.',evidence:[{index:0,quote:'Keep the observed project callable interface.',role:'user'}]}];
      const result=await judge.validate('memory',evidence,candidates,[]),review=result.candidateReview;
      console.log(JSON.stringify({complete:review?.complete,keysMatch:review&&JSON.stringify(Object.keys(review.checkQuestions))===JSON.stringify(Object.keys(review.checkObservations)),questionsExact:review&&Object.entries(review.checkQuestions).every(([k,q])=>JSON.stringify(q)===JSON.stringify(questions[k])),windows:review?.counterWindows,observations:review?.checkObservations}));
    ''')
    assert value.get('complete') and value['keysMatch'] and value['questionsExact'], str(value)
    assert value['windows'] and value['observations']


def test_unbounded_support_keeps_original_execution_context_without_adding_citations():
    value = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const build=expression=>({schemaVersion:1,contextEnabled:true,entries:[
        {role:'user',content:'Keep the observed callable property result as bounded project knowledge.'},
        {role:'assistant',content:[{type:'toolCall',id:'w',name:'write',arguments:{path:'probe.js',content:'const receiver = createCallable(); console.log("property:", '+expression+');'}}]},
        {role:'toolResult',toolName:'write',toolCallId:'w',isError:false,content:'Successfully wrote probe.js'},
        {role:'assistant',content:[{type:'toolCall',id:'b',name:'bash',arguments:{command:'node probe.js'}}]},
        {role:'toolResult',toolName:'bash',toolCallId:'b',isError:false,content:'property: false'},
        {role:'assistant',customType:'continual-learning-memory-reference',content:'INJECTED_REFERENCE_MUST_NOT_REENTER'},
        {role:'assistant',content:[{type:'toolCall',id:'m',name:'read',arguments:{path:'.memory/old.md'}}]},
        {role:'toolResult',toolName:'read',toolCallId:'m',isError:false,content:'Old Memory reference, not independent source.'}
      ]});
      const candidate={name:'probe.md',kind:'project',classification:'safe',content:'---\nname: probe\ndescription: Observed callable property\ntype: project\n---\nThe executed probe reported that "flush" in receiver was false.',evidence:[{index:4,quote:'property: false',role:'toolResult'}]};
      const run=async(expression,bounded=false,mode='normal')=>{
        const evidence=build(expression),item=structuredClone(candidate),before=JSON.stringify({evidence,item});
        if(mode==='secret')evidence.entries.push({role:'user',content:'api_key: abcdefghijklmnop'});
        if(mode==='memory-citation')item.evidence=[{index:7,quote:'Old Memory reference, not independent source.',role:'toolResult'}];
        if(mode==='false-invocation')item.content+=' The returned callable was invoked.';
        if(mode==='late')evidence.entries.push({role:'user',content:'Later unrelated audit context '+'.'.repeat(24000)});
        const requests=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',allowPrivateMemory:true,requestConcurrency:1,...(bounded?{maxRequestBytes:64000}:{}),fetch:async(_url,init)=>{
          const text=String(init.body),r=JSON.parse(text);requests.push({text,payload:r,state:typeof r.state==='string'?JSON.parse(r.state):r.state});
          return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
            const labels=Object.keys(q.criteria);let label=['grounded','compatible','independent','unrelated'].find(x=>labels.includes(x))??labels[0];
            if(mode==='false-invocation' && key==='supported_0')label='unsupported';
            return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===label)]))}];
          }))}));
        }});
        const result=await judge.validate('memory',evidence,mode==='mixed'?[item,{...item,name:'old.md',kind:'rewrite'}]:[item],mode==='mixed'?[{...item,name:'old.md'}]:[]);const support=requests.find(x=>x.payload.questions.supported_0),context=support?.state.originalTaskContext;
        return {decision:result.decision,reason:result.telemetry.reason,calls:requests.length,context,
          frozen:support?.state.frozenEvidence,citations:support?.state.originalCitationsByCandidate?.['0'],
          finiteHash:support?createHash('sha256').update(support.text).digest('hex'):null,
          instruction:support?.payload.questions.supported_0.instructions.question,
          otherContext:requests.filter(x=>!Object.keys(x.payload.questions).every(k=>/^(?:supported(?:_description)?_\d+|counter(?:_description)?_\d+_\d+)$/.test(k))).some(x=>Object.hasOwn(x.state,'originalTaskContext')),
          counters:requests.filter(x=>Object.keys(x.payload.questions).some(k=>/^counter_\d+_\d+$/.test(k))).map(x=>({keys:Object.keys(x.payload.questions),context:x.state.originalTaskContext,windowIndexes:x.state.reviewEvidence.entries.map(e=>e.index),supportIndexes:x.state.supportEvidence.entries.map(e=>e.index),instructions:Object.values(x.payload.questions).map(q=>q.instructions.question)})),
          unchanged:mode==='normal'?before===JSON.stringify({evidence,item}):true};
      };
      const normal=await run('"flush" in receiver'),other=await run('false'),finite=await run('"flush" in receiver',true),secret=await run('"flush" in receiver',false,'secret'),memory=await run('"flush" in receiver',false,'memory-citation'),falseInvocation=await run('"flush" in receiver',false,'false-invocation');
      const late=await run('\"flush\" in receiver',false,'late');
      const mixed=await run('\"flush\" in receiver',false,'mixed');
      console.log(JSON.stringify({normal,other,finite,secret,memory,falseInvocation,late,mixed}));
    ''')
    normal, other, finite = value['normal'], value['other'], value['finite']
    assert normal.get('context'), {'finiteHash': finite['finiteHash'], 'normalContextPresent': bool(normal.get('context'))}
    assert [entry['index'] for entry in normal['context']['entries']] == [0, 1, 2, 3, 4, 6, 7]
    assert normal['context']['entries'][1]['entry']['content'][0]['arguments']['content'] != other['context']['entries'][1]['entry']['content'][0]['arguments']['content']
    assert normal['frozen'] == other['frozen']
    assert [entry['index'] for entry in normal['frozen']['entries']] == [4]
    assert normal['citations'] == [{'index': 4, 'quote': 'property: false', 'role': 'toolResult'}]
    reference = next(entry for entry in normal['context']['entries'] if entry['index'] == 7)
    assert reference['citationEligible'] is False
    assert reference['sourceKind'] == 'memory-reference-or-mixed-output'
    assert {call['resultIndex'] for call in normal['context']['citationToolCalls']} == {2, 4, 7}
    assert 'originalTaskContext' in normal['instruction']
    assert not normal['otherContext'] and not finite.get('context')
    assert finite['finiteHash'] == '022acb2bf48aa8a53c0af2046a946e33ecbcb985f289aac49e8b350df2e81aee'
    assert normal['unchanged'] and other['unchanged'] and finite['unchanged']
    assert value['secret']['calls'] == 0 and value['secret']['reason'] == 'sensitive'
    assert value['memory']['calls'] == 0
    assert value['falseInvocation']['decision'] == 'propose'

    late = value['late']
    late_window = next(counter for counter in late['counters'] if 1 not in counter['windowIndexes'])
    assert late_window.get('context'), {'window': late_window['windowIndexes'], 'support': late_window['supportIndexes']}
    assert late_window['context']['entries'][1]['index'] == 1
    assert late_window['context']['entries'][2]['entry']['content'] == 'Successfully wrote probe.js'
    assert late_window['supportIndexes'] == [4]
    assert all(counter.get('context') == normal['context'] for counter in normal['counters'])
    assert all(not counter.get('context') for counter in finite['counters'])
    assert all('originalTaskContext' in question for question in late_window['instructions'])
    assert all('cannot add support' in question and 'cannot override' in question for question in late_window['instructions'])

    assert value['mixed']['counters']
    assert all(not counter.get('context') for counter in value['mixed']['counters'])
