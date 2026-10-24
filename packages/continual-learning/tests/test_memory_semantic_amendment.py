import pytest
from support import isolated_run_bun


def test_bound_no_entry_does_not_erase_existing_or_omitted_candidates():
    # Given optional and required held candidates, When an explicit refusal is
    # parent-authorized, Then remove only that never-written proposal.
    result = isolated_run_bun(r'''
      import {bindSemanticMemoryAmendment,mergeSemanticMemoryRepairDelta,semanticMemoryRepairCandidates} from './packages/continual-learning/extensions/inject-memory.ts';
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'required.md',kind:'project',classification:'private',content:'Required contract.',evidence:[{index:0,quote:'Required contract.'}]};
      const b={...a,name:'optional.md',content:'A single unresolved timing observation.'};
      const old={...a,name:'existing.md',kind:'rewrite'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[old],newMemories:[a,b]};
      const candidates=semanticMemoryRepairCandidates(original),id=candidates.find(x=>x.name===b.name).candidateId;
      const response={kind:'incremental-memory-amendment',version:1,...identity,replacements:[],withdrawals:[{candidateId:id,reason:'not-reusable'}]};
      const bound=bindSemanticMemoryAmendment(original,response,identity,[a.name,b.name],undefined,[b.name]);
      const merged=mergeSemanticMemoryRepairDelta(original,bound,[a.name,b.name],undefined,undefined,[b.name]);
      const rejects=(value,names=[b.name])=>{try{bindSemanticMemoryAmendment(original,value,identity,[old.name,a.name,b.name],undefined,names);return false}catch{return true}};
      const mutation={...response,replacements:[{candidateId:id,content:'changed',evidence:b.evidence}]};
      const omitted=mergeSemanticMemoryRepairDelta(original,bindSemanticMemoryAmendment(original,{...response,withdrawals:[]},identity));
      console.log(JSON.stringify({names:merged.newMemories.map(x=>x.name),sameOld:JSON.stringify(merged.operations)===JSON.stringify(original.operations),
        notMutationField:!('withdrawals' in merged),omitted:omitted.newMemories.length,
        blocked:[rejects(response,[]),rejects({...response,runId:'foreign'}),rejects(mutation),
          rejects({...response,withdrawals:[...response.withdrawals,...response.withdrawals]}),
          rejects({...response,withdrawals:[{candidateId:candidates[0].candidateId,reason:'not-reusable'}]},[old.name]),
          rejects({...response,withdrawals:[{candidateId:id,reason:'invented'}]}),
          rejects({...response,withdrawals:[{candidateId:id,reason:'not-reusable',name:b.name}]})]}));
    ''')
    assert result['names'] == ['required.md']
    assert result['sameOld'] and result['notMutationField'] and result['omitted'] == 2
    assert all(result['blocked'])


@pytest.mark.parametrize('native', [False, True])
def test_explicit_optional_draft_refusal_survives_native_framing_and_rechecks_absence(tmp_path, native):
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import path from 'node:path';import fs from 'node:fs';import {spawnSync} from 'node:child_process';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kit=await import('./packages/kit/src/index.ts');let mode='valid',calls=0,checks=0,lastContext;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;const data=JSON.parse(input.prompt.split('\n').at(-1));lastContext=data;
        const reply={kind:'incremental-memory-amendment',version:1,...data.identity,replacements:[],
          withdrawals:mode==='empty'?[]:[{candidateRef:data.repairCandidates[0].candidateRef,reason:'not-reusable'}]};
        if(NATIVE && mode==='valid'){
          const cli=path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');
          const version=spawnSync('node',[cli,'--version'],{encoding:'utf8'});if(version.status!==0||version.stdout.trim()!=='1.3.0')throw Error('Pi1.3 required');
          const r=spawnSync('node',[cli,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
            '--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','--bound-candidate-response',JSON.stringify(reply),input.prompt],
            {cwd:ROOT,env:{PATH:process.env.PATH,HOME:ROOT,PI_CODING_AGENT_DIR:path.join(ROOT,'agent'),PI_OFFLINE:'1'},encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
          fs.writeFileSync(path.join(ROOT,'native-no-entry-output.jsonl'),r.stdout);
          if(r.status!==0)throw Error(r.stderr+'\n'+r.stdout);
          return {...kit.parsePiWorkerOutput(r.stdout),exitCode:0,stderr:'',cancelled:false};
        }
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify(reply),usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:.1}};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const snapshot={contextEnabled:true,runId:'r',scopeKey:'s',scopeDigest:'d',entries:[{role:'user',content:'Optional observation.'}]};
      const h=sha256Digest(JSON.stringify(snapshot,null,2)+'\n'),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:h,snapshotDigest:h};
      const candidate={name:'optional.md',kind:'project',classification:'private',content:'---\nname: optional\ndescription: Optional observation.\ntype: project\n---\nOptional observation.',evidence:[{ref:'e0.b0.l1'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]},before=JSON.stringify(original);
      const input={identity,rejectedPlan:original,selectedNames:[],repairableNames:['optional.md'],repairableFields:{'optional.md':['body']},errors:['held'],
        withdrawableNames:['optional.md'],assertWithdrawalsUnwritten:async()=>{checks++;if(mode==='race'&&checks===2||mode==='exists')throw Error('already exists');},
        semanticContext:{frozenEvidence:snapshot,existingMemories:[]}};
      const rows=[];for(mode of ['valid','empty','race','exists','required']){
        checks=0;const count=calls;const r=await repairIncrementalMemoryPlan(mode==='required'?{...input,withdrawableNames:[]}:input);
        rows.push({mode,outcome:r.outcome,failureKind:r.failureKind,declined:r.declinedNewMemories,newCount:r.plan?.newMemories.length,checks,calls:calls-count,
          advertised:lastContext?.repairCandidates[0].withdrawalAllowed===true});
      }
      console.log(JSON.stringify({rows,unchanged:before===JSON.stringify(original),memoryWritten:fs.existsSync(path.join(ROOT,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE', str(native).lower()))
    first = result['rows'][0]
    assert first['outcome'] == 'repaired' and first['declined'] == ['optional.md'] and first['newCount'] == 0, first
    assert first['checks'] == 2 and first['advertised']
    assert all(row['outcome'] == 'failed' for row in result['rows'][1:]), result
    assert result['rows'][3]['calls'] == 0 and not result['rows'][4]['advertised']
    assert result['unchanged'] and not result['memoryWritten']


def test_real_repair_cannot_discard_maintenance_sections():
    # Given V77's actual purpose loss, When repairing a held candidate,
    # Then retain its populated purpose slots without locking their old claims.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-purpose-loss.json','utf8'));
      const original={operations:[],newMemories:[f.original]},name=f.original.name;
      const merge=(content,fields=['body','description'],prior=f.original)=>mergeSemanticMemoryRepairDelta(
        {...original,newMemories:[prior]}, {operations:[],newMemories:[{...f.repaired,content}]}, [name],
        fields===null?undefined:{[name]:fields});
      const rejected=(content,fields)=>{try{merge(content,fields);return false}catch{return true}};
      const corrected=f.repaired.content+'\n**Why**: Compare this observed declaration during later maintenance.\n\n**How to apply**:\nUse the current declarations when the API changes; the old input constraint is not permanent.\n';
      const legacy={...f.original,content:f.repaired.content};
      const fake=legacy.content+'\n```md\n**Why**: A quoted heading is not a purpose slot.\n**How to apply**: Nor is this.\n```\n';
      const crlf=corrected.replaceAll('\n','\r\n');
      const atx=f.repaired.content+'\n## Why\nCompare the observed contract.\n\n## How to apply\nCheck later source before maintenance.\n';
      const empty=f.repaired.content+'\n**Why**:\n\n**How to apply**:\n\n## Notes\nUnrelated text cannot fill either slot.\n';
      const breaks=f.repaired.content+'\n**Why**:\n---\n**How to apply**:\n* * *\n';
      const comments=f.repaired.content+'\n**Why**:\n<!-- no purpose -->\n**How to apply**:\n<!-- no guidance -->\n';
      const commented=legacy.content+'\n<!--\n**Why**: Hidden.\n**How to apply**: Hidden too.\n-->\n';
      const codeOnly=legacy.content+'\n**Why**: Later maintenance.\n**How to apply**:\n```ts\nconst result = limitedFunction(1);\n```\n';
      const literal=corrected.replace('Compare this observed declaration','Inspect the literal `<!--` marker in this declaration');
      const multiline=corrected.replace('Compare this observed declaration','Inspect the literal ``line\n<!--\nend`` marker in this declaration');
      const descriptionOnly=merge(f.repaired.content,['description']);
      const actualFailures = f.additionalCases.map(c => {
        try {mergeSemanticMemoryRepairDelta({operations:[],newMemories:[c.original]},
          {operations:[],newMemories:[c.repaired]},[c.original.name],{[c.original.name]:['body','description']});return false}
        catch{return true}
      });
      const inside=corrected.replaceAll('**Why**:', '**Why:**').replaceAll('**How to apply**:', '**How to apply:**');
      const insideEmpty=empty.replaceAll('**Why**:', '**Why:**').replaceAll('**How to apply**:', '**How to apply:**');
      const insideOtherHeading=f.repaired.content+'\n**Why:** Later maintenance.\n**How to apply:**\n\n**Notes:** Unrelated text.';
      const plain=corrected.replaceAll('**Why**:', 'Why:').replaceAll('**How to apply**:', 'How to apply:');
      const plainEmpty=empty.replaceAll('**Why**:', 'Why:').replaceAll('**How to apply**:', 'How to apply:');
      const plainOtherHeading=f.repaired.content+'\nWhy: Later maintenance.\nHow to apply:\n\nOther section: Unrelated text.';
      const plainQuoted=legacy.content+'\n```md\nWhy: Quoted.\nHow to apply: Quoted too.\n```\n';
      const plainCommented=legacy.content+'\n<!--\nWhy: Hidden.\nHow to apply: Hidden too.\n-->\n';
      const emptyPlainPrior=legacy.content+'\nWhy:\nNotes: Unrelated text.\nHow to apply: Compare declarations.\n';
      const limitsPrior={...legacy,content:legacy.content+'\nLimits for future maintenance: Verify changed behavior with current evidence; preserve still-valid scope.\n'};
      const limitsAccepted=f.repaired.content+'\nHow to apply: Compare current source and equivalent verification; revise obsolete advice with evidence.\n';
      const limitsChecks=[
        (()=>{try{merge(f.repaired.content,['body'],limitsPrior);return false}catch{return true}})(),
        merge(limitsAccepted,['body'],limitsPrior).newMemories[0].content===limitsAccepted,
        ...['## Limits for future maintenance\nInspect current source.','**Limits for future maintenance:** Inspect current source.',
            '**Limits for future maintenance**: Inspect current source.','LIMITS FOR FUTURE MAINTENANCE: Inspect current source.'].map(label=>{
          try{merge(f.repaired.content,['body'],{...legacy,content:legacy.content+'\n'+label+'\n'});return false}catch{return true}}),
        (()=>{try{merge(f.repaired.content,['body'],{...limitsPrior,content:limitsPrior.content.replaceAll('\n','\r\n')});return false}catch{return true}})(),
        ...['```md\nLimits for future maintenance: Quoted.\n```','<!--\nLimits for future maintenance: Hidden.\n-->',
            'Limits for future maintenance:\nNotes: Unrelated text.'].map(text=>merge(f.repaired.content,['body'],{...legacy,content:legacy.content+'\n'+text+'\n'}).newMemories.length===1),
      ];
      const before=JSON.stringify(f);
      console.log(JSON.stringify({actualFailures,limitsChecks,
        plainAccepted:merge(plain).newMemories[0].content===plain,
        plainCrlfAccepted:merge(plain.replaceAll('\n','\r\n')).newMemories[0].content.includes('Why: Compare'),
        plainEmptyRejected:rejected(plainEmpty),plainOtherHeadingRejected:rejected(plainOtherHeading),
        plainQuotedIgnored:merge(f.repaired.content,['body'],{...legacy,content:plainQuoted}).newMemories.length===1,
        plainCommentedIgnored:merge(f.repaired.content,['body'],{...legacy,content:plainCommented}).newMemories.length===1,
        plainEmptyNotInvented:merge(f.repaired.content+'\nHow to apply: Compare declarations.\n',['body'],{...legacy,content:emptyPlainPrior}).newMemories.length===1,insideAccepted:(()=>{try{return merge(inside).newMemories[0].content===inside}catch{return false}})(),
        insideEmptyRejected:rejected(insideEmpty),insideOtherHeadingRejected:rejected(insideOtherHeading),dropped:rejected(f.repaired.content),broad:rejected(f.repaired.content,null),
        lostWhy:rejected(corrected.replace(/\*\*Why\*\*:[^\n]*\n/,'')),
        lostHow:rejected(corrected.replace(/\*\*How to apply\*\*:[\s\S]*$/,'')),
        empty:rejected(empty),breaks:rejected(breaks),comments:rejected(comments),fake:rejected(fake),
        corrected:merge(corrected).newMemories[0].content===corrected,
        crlf:merge(crlf).newMemories[0].content.endsWith(crlf.split('---\r\n').at(-1)),
        atx:merge(atx).newMemories[0].content===atx,
        descriptionBody:descriptionOnly.newMemories[0].content.endsWith(f.original.content.split('---\n').at(-1)),
        legacy:merge(f.repaired.content,['body','description'],legacy).newMemories.length===1,
        quotedOnly:merge(f.repaired.content,['body'],{...legacy,content:fake}).newMemories.length===1,
        commented:merge(f.repaired.content,['body'],{...legacy,content:commented}).newMemories.length===1,
        codePreserved:(()=>{try{merge(f.repaired.content+'\n**Why**: Later maintenance.\n',['body'],{...legacy,content:codeOnly});return false}catch{return true}})(),
        inlineAccepted:(()=>{try{return merge(literal).newMemories.length===1}catch{return false}})(),
        multilineAccepted:(()=>{try{return merge(multiline).newMemories.length===1}catch{return false}})(),
        inlineLossRejected:(()=>{try{merge(f.repaired.content+'\n**Why**: Later maintenance.\n',['body'],{...legacy,content:literal});return false}catch{return true}})(),
        unchanged:before===JSON.stringify(f)}));
    ''')
    assert result['actualFailures'] == [True, True, True]
    assert all(result['limitsChecks'])
    for key in ('plainAccepted', 'plainCrlfAccepted', 'plainEmptyRejected', 'plainOtherHeadingRejected', 'plainQuotedIgnored', 'plainCommentedIgnored', 'plainEmptyNotInvented', 'insideAccepted', 'insideEmptyRejected', 'insideOtherHeadingRejected', 'dropped', 'broad', 'lostWhy', 'lostHow', 'empty', 'breaks', 'comments', 'fake', 'corrected',
                'crlf', 'atx', 'descriptionBody', 'legacy', 'quotedOnly', 'commented', 'codePreserved',
                'inlineAccepted', 'multilineAccepted', 'inlineLossRejected', 'unchanged'):
        assert result[key], (key, result)


def test_retained_repair_preserves_purpose_slots_without_blocking_deletion():
    # Given an existing record with usage context, When the retained correction
    # path rewrites or deletes it, Then only rewrites retain its purpose slots.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let mode,prompt;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const header='---\nname: Example\ndescription: Source contract.\ntype: project\n---\n';
      const slots='\n**Why**: Compare later maintenance.\n**How to apply**: Inspect current source.\n';
      const prior={name:'a.md',classification:'private',type:'project',content:header+'Old source contract.'+slots};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;
        const operation=mode==='delete'?{name:'a.md',kind:'delete',classification:'private',verdict:'SUPERSEDED',preservedIn:['index.d.ts'],evidence:[{index:0,quote:'Correct source contract.'}]}:
          {name:'a.md',kind:'rewrite',classification:'private',content:header+'Correct source contract.'+(mode==='corrected'?slots:''),evidence:[{index:0,quote:'Correct source contract.'}]};
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[operation],newMemories:[]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const rows=[];for(mode of ['dropped','corrected','delete']){
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:{kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]},
          selectedNames:['a.md'],retainedRepairNames:['a.md'],errors:['held'],
          semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Correct source contract.'}]},existingMemories:[prior]}});
        rows.push({mode,outcome:result.outcome,failureKind:result.failureKind,hasPlan:!!result.plan,
          sections:JSON.parse(prompt.split('\n').at(-1)).retainedOperationContract.records[0].requiredKnowledgeSections,
          instruction:prompt.includes('not to an otherwise authorized delete operation')});
      }
      console.log(JSON.stringify(rows));
    ''')
    assert result[0]['outcome'] == 'failed' and result[0]['failureKind'] == 'intent' and not result[0]['hasPlan']
    assert all(row['outcome'] == 'repaired' for row in result[1:]), result
    assert all(row['sections'] == ['Why', 'How to apply'] and row['instruction'] for row in result), result


def test_semantic_noop_normalizes_citation_order_and_inferred_roles():
    # Given a held proposal, When a patch only reorders the same valid sources,
    # Then retain failure and usage; real body or source changes remain reviewable.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kit=await import('./packages/kit/src/index.ts');let mode;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const data=JSON.parse(input.prompt.split('\n').at(-1)),candidate=data.repairCandidates[0],prior=data.rejectedPlan.newMemories[0];
        const source=mode==='new-source'?[...prior.evidence,{index:2,quote:'Source C.'}]
          :mode==='reordered-roles'?[...prior.evidence].reverse().map(e=>({...e,role:'user'})):prior.evidence;
        return {exitCode:0,stderr:'',cancelled:false,usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:0.1},
          text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...data.identity,replacements:[{
            candidateRef:candidate.candidateRef,content:mode==='description'?prior.content.replace('description: Source A.','description: Source B.'):prior.content+(mode==='body'?'\nSource B.':''),evidence:source}]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const snapshot={contextEnabled:true,runId:'r',scopeKey:'s',scopeDigest:'d',entries:['Source A.','Source B.','Source C.'].map(content=>({role:'user',content}))};
      const h=sha256Digest(JSON.stringify(snapshot,null,2)+'\n'),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:h,snapshotDigest:h};
      const candidate={name:'a.md',kind:'project',classification:'private',content:'---\nname: a.md\ndescription: Source A.\ntype: project\n---\nSource A.',
        evidence:[{index:0,quote:'Source A.'},{index:1,quote:'Source B.'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]},before=JSON.stringify(original),rows=[];
      for(mode of ['same','reordered-roles','body','description','new-source']){
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[],repairableNames:['a.md'],repairableFields:{'a.md':['body','description']},errors:['held'],
          semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
        rows.push({mode,outcome:result.outcome,failureKind:result.failureKind,usage:result.usage,plan:!!result.plan});
      }
      console.log(JSON.stringify({rows,unchanged:before===JSON.stringify(original)}));
    ''')
    assert result['unchanged']
    for row in result['rows']:
        if row['mode'] in ('same', 'reordered-roles'):
            assert row['outcome'] == 'failed' and row['failureKind'] == 'no-correction' and not row['plan'], row
        else:
            assert row['outcome'] == 'repaired' and row['plan'], row
        assert row['usage']['cost'] == 0.1 and row['usage']['totalTokens'] == 5


@pytest.mark.parametrize('native', [False, True])
def test_real_candidate_copy_failure_uses_exact_parent_bound_refs(tmp_path, native):
    import json
    # Given V52's malformed full ID, When a fresh worker explicitly selects a
    # short parent-bound reference, Then bind exact originals without repairing
    # the historical response or granting semantic approval.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-candidate-copy.json','utf8'));
      const original=f.files['semantic-rejected-plan.json'].value,raw=f.files['repair-response.json'].value.output;
      const snapshot=f.files['snapshot.json'].value,kit=await import('./packages/kit/src/index.ts');let prompt,mode='original',calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;prompt=input.prompt;
        if(mode==='original')return {exitCode:0,stderr:'',text:raw,cancelled:false};
        const data=JSON.parse(prompt.split('\n').at(-1)),reply=JSON.parse(raw);
        reply.replacements=reply.replacements.map((patch,i)=>{const {candidateId,...rest}=patch;return {...rest,candidateRef:data.repairCandidates[i].candidateRef}});
        if(NATIVE){
          const root=ROOT,cli=path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');
          const version=spawnSync('node',[cli,'--version'],{encoding:'utf8'});if(version.status!==0||version.stdout.trim()!=='1.3.0')throw Error('Pi1.3 required');
          const native=spawnSync('node',[cli,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
            '--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','--bound-candidate-response',JSON.stringify(reply),input.prompt],{cwd:root,env:{PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'},encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
          fs.writeFileSync(path.join(root,'native-prompt.txt'),input.prompt);fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);fs.writeFileSync(path.join(root,'native-version.txt'),version.stdout);
          if(native.status!==0)throw Error(native.stderr+'\n'+native.stdout.slice(-4000));
          return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
        }
        return {exitCode:0,stderr:'',text:JSON.stringify(reply),cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {containsSensitiveMemoryMaterial}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const names=original.newMemories.map(x=>x.name),retained=f.existing[0].name,before=JSON.stringify(f);
      const input={identity,rejectedPlan:original,selectedNames:[retained],errors:['held'],repairableNames:names,
        repairableFields:Object.fromEntries(names.map(n=>[n,['body','description']])),retainedRepairNames:[retained],
        semanticContext:{frozenEvidence:snapshot,existingMemories:f.existing}};
      const historical=await repairIncrementalMemoryPlan(input);mode='reference';const referenced=await repairIncrementalMemoryPlan(input);
      const candidates=semanticMemoryRepairCandidates(original),failed=JSON.parse(raw);
      console.log(JSON.stringify({historical,referenced,unchanged:before===JSON.stringify(f),sensitive:containsSensitiveMemoryMaterial(JSON.stringify(f)),
        validMarkdown:failed.replacements.every(x=>x.content.startsWith('---\n')),hashLengths:failed.replacements.map(x=>x.candidateId.split(':').at(-1).length),
        fullHashes:candidates.map(x=>x.candidateId.split(':').at(-1).length),refs:JSON.parse(prompt.split('\n').at(-1)).repairCandidates.map(x=>x.candidateRef),calls,
        memoryWritten:fs.existsSync(path.join(ROOT,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE',str(native).lower()))
    assert result['unchanged'] and not result['sensitive'] and result['validMarkdown']
    assert result['hashLengths'] == [64, 61] and result['fullHashes'] == [64, 64]
    assert result['historical']['failureKind'] == 'intent' and 'plan' not in result['historical']
    assert result['referenced']['outcome'] == 'repaired', result['referenced']
    assert result['refs'] == ['newMemories:0', 'newMemories:1']
    assert len(result['referenced']['plan']['newMemories']) == 2
    assert len(result['referenced']['plan']['operations']) == 1
    assert result['calls'] == 2 and not result['memoryWritten']


def test_candidate_refs_preserve_complete_parent_identity_and_stale_input_guards():
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {bindSemanticMemoryAmendment,bindMemoryCitationAmendment,semanticMemoryRepairCandidates} from './packages/continual-learning/extensions/inject-memory.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-candidate-copy.json','utf8'));
      const original=f.files['semantic-rejected-plan.json'].value,snapshot=f.files['snapshot.json'].value,raw=JSON.parse(f.files['repair-response.json'].value.output);
      const candidates=semanticMemoryRepairCandidates(original),names=candidates.map(x=>x.name);
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const {operations,...response}=raw;
      const amendment={...response,replacements:response.replacements.map(({candidateId,...patch},i)=>({...patch,candidateRef:`newMemories:${i}`}))};
      const sources={frozenEvidence:snapshot,repairableFields:Object.fromEntries(names.map(n=>[n,['body','description']])),
        candidateBinding:{proposalDigest:sha256Digest(JSON.stringify(original)),references:candidates.map(c=>({ref:`${c.field}:${c.index}`,candidateId:c.candidateId}))}};
      const bind=(o,a,s=sources)=>bindSemanticMemoryAmendment(o,a,identity,names,s),rejects=(o,a,s=sources)=>{try{bind(o,a,s);return false}catch{return true}};
      const good=bind(original,amendment),invalid={};
      for(const key of Object.keys(identity))invalid['identity-'+key]=rejects(original,{...amendment,[key]:'foreign'});
      invalid.missingIdentity=rejects(original,{...amendment,runId:undefined});invalid.version=rejects(original,{...amendment,version:2});
      invalid.noBinding=rejects(original,amendment,{...sources,candidateBinding:undefined});
      invalid.foreignDigest=rejects(original,amendment,{...sources,candidateBinding:{...sources.candidateBinding,proposalDigest:'foreign'}});
      invalid.changedMap=rejects(original,amendment,{...sources,candidateBinding:{...sources.candidateBinding,references:[...sources.candidateBinding.references].reverse()}});
      invalid.changedSnapshot=rejects(original,amendment,{...sources,frozenEvidence:{...snapshot,entries:snapshot.entries.slice(1)}});
      for(const [label,change] of Object.entries({body:x=>x.newMemories[0].content+=' changed',privacy:x=>x.newMemories[0].classification='private',
        source:x=>x.newMemories[0].evidence=[],order:x=>x.newMemories.reverse()})){
        const changed=structuredClone(original);change(changed);invalid[label]=rejects(changed,amendment);
      }
      const first=amendment.replacements[0];
      for(const [label,patches] of Object.entries({unknownRef:[{...first,candidateRef:'newMemories:99'}],mixedSelector:[{...first,candidateId:candidates[0].candidateId}],
        missingSelector:[{content:first.content,evidence:first.evidence}],foreignProperty:[{...first,classification:'private'}],
        duplicateRef:[first,first],duplicateAliasAndId:[first,{candidateId:candidates[0].candidateId,content:first.content,evidence:first.evidence}]})){
        invalid[label]=rejects(original,{...amendment,replacements:patches});
      }
      invalid.originalMalformedId=rejects(original,response);
      try{bindMemoryCitationAmendment(original,amendment,identity);invalid.citationOnly=false}catch{invalid.citationOnly=true}
      console.log(JSON.stringify({invalid,good:good.newMemories.map(x=>x.name),original:original.newMemories.map(x=>x.name),unchangedContent:good.newMemories.every((x,i)=>x.content===raw.replacements[i].content)}));
    ''')
    assert all(result['invalid'].values()), result['invalid']
    assert result['good'] == result['original'] and result['unchangedContent']


def test_candidate_binding_is_captured_before_the_worker_and_cannot_drift():
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-candidate-copy.json','utf8'));
      const original=f.files['semantic-rejected-plan.json'].value,snapshot=f.files['snapshot.json'].value,kit=await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const data=JSON.parse(input.prompt.split('\n').at(-1)),reply=JSON.parse(f.files['repair-response.json'].value.output);
        reply.replacements=reply.replacements.map(({candidateId,...patch},i)=>({...patch,candidateRef:data.repairCandidates[i].candidateRef}));
        original.newMemories[0].content+=' changed while worker ran';
        return {exitCode:0,stderr:'',text:JSON.stringify(reply),cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const names=original.newMemories.map(x=>x.name),retained=f.existing[0].name;
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[retained],errors:['held'],repairableNames:names,
        repairableFields:Object.fromEntries(names.map(n=>[n,['body','description']])),retainedRepairNames:[retained],semanticContext:{frozenEvidence:snapshot,existingMemories:f.existing}});
      console.log(JSON.stringify(result));
    ''')
    assert result['outcome'] == 'failed' and result['failureKind'] == 'intent' and 'plan' not in result


@pytest.mark.parametrize('native', [False, True])
def test_real_stale_repair_can_select_exact_parent_audited_source_without_regeneration(tmp_path, native) -> None:
    import json
    # Given V50's full retained evidence, When a controlled worker explicitly
    # selects its newer declaration, Then copy observed bytes, preserve metadata,
    # and keep the historical failed response and all semantic gates separate.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const root=ROOT,fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-source-order.json','utf8'));
      fs.writeFileSync(path.join(root,'index.d.ts'),fixture.sourceFiles['index.d.ts']);
      const rebase=v=>typeof v==='string'?v.replaceAll('/work/p-limit',root):Array.isArray(v)?v.map(rebase):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,rebase(x)])):v;
      const snapshot=rebase(fixture.snapshot),original=rebase(fixture.original),existing=rebase(fixture.existing);
      const snapshotDigest=sha256Digest(JSON.stringify(snapshot,null,2)+'\n');original.snapshotDigest=snapshotDigest;original.artifactHash=snapshotDigest;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const sources={evidenceDigest:sha256Digest(JSON.stringify(snapshot)),entryDigests:fixture.sourceEntryIndexes.map(i=>sha256Digest(JSON.stringify(snapshot.entries[i])))};
      const run={manifest:{cwd:root,...identity}},kit=await import('./packages/kit/src/index.ts');let prompt,mode='valid',calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;prompt=input.prompt;const context=JSON.parse(prompt.split('\n').at(-1)),candidate=context.repairCandidates[0];
        if(NATIVE && calls<=2){
          const cli=path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');
          const version=spawnSync('node',[cli,'--version'],{encoding:'utf8'});if(version.status!==0||version.stdout.trim()!=='1.3.0')throw Error('Pi1.3 required');
          const env={PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'};
          const native=spawnSync('node',[cli,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
            '--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','--source-excerpt-selection',JSON.stringify({ref:'e56.b0.l146',endRef:'e56.b0.l149'}),input.prompt],{cwd:root,env,encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
          fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);fs.writeFileSync(path.join(root,'native-prompt.txt'),input.prompt);
          fs.writeFileSync(path.join(root,'native-version.txt'),version.stdout);
          if(native.status!==0)throw Error(JSON.stringify({status:native.status,signal:native.signal,error:String(native.error),stderr:native.stderr,stdoutTail:native.stdout.slice(-4000)}));
          return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
        }
        const patch={candidateId:candidate.candidateId,sourceExcerpt:{ref:'e56.b0.l146',endRef:'e56.b0.l149'},evidence:[{ref:'e56.b0.l146',endRef:'e56.b0.l149'}]};
        const response={kind:'incremental-memory-amendment',version:1,...identity,replacements:[patch]};
        if(mode==='mixed')patch.content='old';if(mode==='noEvidence')delete patch.evidence;if(mode==='foreign')patch.candidateId='foreign';
        if(mode==='ordinaryRead'){patch.sourceExcerpt={ref:'e3.b0.l1',endRef:'e3.b0.l3'};patch.evidence=[patch.sourceExcerpt]}
        if(mode==='uncovered')patch.evidence=[{ref:'e56.b0.l1'}];if(mode==='noIdentity')delete response.runId;
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify(response)};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const name=original.operations[0].name;
      const input={identity,rejectedPlan:original,errors:['held body'],selectedNames:existing.map(x=>x.name),repairableNames:[name],repairableFields:{[name]:['body']},
        memorySources:sources,sourceExcerptRun:run,semanticContext:{frozenEvidence:snapshot,existingMemories:existing},outputDir:root};
      const good=await repairIncrementalMemoryPlan(input),context=JSON.parse(prompt.split('\n').at(-1));
      const saved=JSON.parse(fs.readFileSync(path.join(root,'repair-response.json'),'utf8'));
      // Given the same already-rejected excerpt, When the repair selects the
      // same source again, Then retain failure and usage without a second review.
      const repeated=await repairIncrementalMemoryPlan({...input,rejectedPlan:good.plan});
      const rejected={};for(const value of ['mixed','noEvidence','foreign','uncovered','noIdentity','ordinaryRead']){mode=value;rejected[value]=(await repairIncrementalMemoryPlan(input)).outcome}
      let purposeExcerptAllowed,purposeLimitsExcerptAllowed;mode='valid';for(const [key,change] of Object.entries({noRun:x=>delete x.sourceExcerptRun,noAudit:x=>delete x.memorySources,
        locked:x=>x.repairableFields={[name]:['description']},wrongRun:x=>x.sourceExcerptRun={manifest:{...run.manifest,runId:'foreign'}},
        wrongSnapshot:x=>x.semanticContext={...x.semanticContext,frozenEvidence:{...snapshot,runId:'foreign'}},
        safe:x=>x.rejectedPlan={...original,operations:original.operations.map(o=>({...o,classification:'safe'}))},
        purposeLimits:x=>x.rejectedPlan={...original,operations:original.operations.map(o=>({...o,content:o.content+'\nLimits for future maintenance: Compare current source.'}))},
        purpose:x=>x.rejectedPlan={...original,operations:original.operations.map(o=>({...o,content:o.content+'\n**Why**: Later maintenance.\n**How to apply**: Compare current source.\n'}))},
        preference:x=>x.semanticContext={...x.semanticContext,existingMemories:existing.map(o=>({...o,type:'preference'}))}})){
          const x={...input};change(x);rejected[key]=(await repairIncrementalMemoryPlan(x)).outcome;
          if(key==='purposeLimits')purposeLimitsExcerptAllowed=JSON.parse(prompt.split('\n').at(-1)).repairCandidates[0].sourceExcerptAllowed===true;
          if(key==='purpose')purposeExcerptAllowed=JSON.parse(prompt.split('\n').at(-1)).repairCandidates[0].sourceExcerptAllowed===true;}
      console.log(JSON.stringify({good,repeated,rejected,purposeExcerptAllowed,purposeLimitsExcerptAllowed,context:{repairCandidates:context.repairCandidates},saved,old:original.operations[0],historical:fixture.response.replacements[0],calls,
        memoryWritten:fs.existsSync(path.join(root,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE', str(native).lower()))
    assert result['good']['outcome'] == 'repaired', result['good']
    assert result['repeated']['outcome'] == 'failed', result['repeated']
    assert result['repeated']['failureKind'] == 'no-correction' and 'plan' not in result['repeated']
    operation = result['good']['plan']['operations'][0]
    assert '"clearQueue" | "onIdle"' in operation['content'] or "'clearQueue' | 'onIdle'" in operation['content']
    assert operation['content'].split('\n---\n')[0] == result['old']['content'].split('\n---\n')[0]
    assert operation['name'] == result['old']['name'] and operation['kind'] == 'rewrite'
    assert operation['classification'] == result['old']['classification'] == 'private'
    assert all(value == 'failed' for value in result['rejected'].values()), result['rejected']
    assert result['context']['repairCandidates'][0]['sourceExcerptAllowed'] is True
    assert result['purposeExcerptAllowed'] is False
    assert result['purposeLimitsExcerptAllowed'] is False
    assert 'sourceExcerpt' in result['saved']['output'] and not result['memoryWritten']
    assert 'onIdle' not in result['historical']['content']


def test_frozen_real_repair_keeps_candidate_identity_parent_owned() -> None:
    # Given the real v31 new->rewrite failure, When correcting held content,
    # Then the parent binds patches to the original proposal and still rejects
    # the actual failed response, foreign IDs, privacy changes and stale input.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {semanticMemoryRepairCandidates,bindSemanticMemoryAmendment,mergeSemanticMemoryRepairDelta,candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-intent-failure.json','utf8'));
      const original=fixture.files['semantic-rejected-plan.json'].value;
      const failed=JSON.parse(fixture.files['repair-response.json'].value.output);
      const snapshot=fixture.files['snapshot.json'].value;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const candidates=semanticMemoryRepairCandidates(original);
      const prior=original.newMemories[0];
      const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:candidates[0].candidateId,content:prior.content,evidence:prior.evidence}]};
      const bound=bindSemanticMemoryAmendment(original,amendment,identity);
      const merged=mergeSemanticMemoryRepairDelta(original,bound);
      const rejects=value=>{try{bindSemanticMemoryAmendment(original,value,identity);return false;}catch{return true;}};
      let oldRejected=false;try{mergeSemanticMemoryRepairDelta(original,failed)}catch{oldRejected=true}
      const invalid=[{...amendment,runId:'other'}, {...amendment,operations:[]},
        {...amendment,replacements:[{...amendment.replacements[0],classification:'safe'}]},
        {...amendment,replacements:[{...amendment.replacements[0],candidateId:'foreign'}]},
        {...amendment,replacements:[amendment.replacements[0],amendment.replacements[0]]}];
      let staleRejected=false;try{bindSemanticMemoryAmendment({...original,newMemories:[{...prior,content:'changed'},...original.newMemories.slice(1)]},amendment,identity)}catch{staleRejected=true}
      let unheldRejected=false;try{bindSemanticMemoryAmendment(original,amendment,identity,[])}catch{unheldRejected=true}
      console.log(JSON.stringify({oldRejected,invalid:invalid.map(rejects),staleRejected,unheldRejected,
        unchanged:JSON.stringify(merged)===JSON.stringify(original),boundOperations:bound.operations,
        candidates,sensitive:containsSensitiveMemoryMaterial(JSON.stringify(fixture)),
        citations:candidateCitationProblems(snapshot,merged.newMemories)}));
    ''')
    assert result['oldRejected']
    assert all(result['invalid'])
    assert result['staleRejected'] and result['unheldRejected']
    assert result['unchanged']
    assert result['boundOperations'] == []
    assert len(result['candidates']) == 2
    assert not result['sensitive']
    assert result['citations'] == []


def test_semantic_worker_uses_bound_amendments_and_preserves_omitted_candidates() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt,tools;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[a,{...a,name:'b.md',content:'B'}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;tools=input.tools;
        const context=JSON.parse(prompt.split('\n').at(-1));
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:context.repairCandidates[0].candidateId,content:'correct A',evidence:a.evidence}]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['a held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}});
      console.log(JSON.stringify({result,prompt,tools}));
    ''')
    assert result['result']['outcome'] == 'repaired'
    assert [x['content'] for x in result['result']['plan']['newMemories']] == ['correct A', 'B']
    assert result['tools'] == []
    assert 'incremental-memory-amendment' in result['prompt']
    assert 'Candidate identity, operation kind and privacy are parent-owned' in result['prompt']


@pytest.mark.parametrize('raw_whitespace', [False, True])
@pytest.mark.parametrize('inside_colon', [False, True, 'plain', 'limits'])
def test_actual_pi_receives_parent_bound_amendment_prompt_without_tools(tmp_path, raw_whitespace, inside_colon) -> None:
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');const root=ROOT;const rawWhitespace=RAW_WHITESPACE;
      const purpose=INSIDE_COLON==='limits'?'\n\nWhy: Later maintenance.\n\nLimits for future maintenance: Compare the current source.':INSIDE_COLON==='plain'?'\n\nWhy: Later maintenance.\n\nHow to apply: Compare the current source.':INSIDE_COLON?'\n\n**Why:** Later maintenance.\n\n**How to apply:** Compare the current source.':'\n\n**Why**: Later maintenance.\n\n**How to apply**: Compare the current source.';
      const header='---\nname: a.md\ndescription: Claim.\ntype: project\n---\n';
      let sections;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        sections=JSON.parse(input.prompt.split('\n').at(-1)).repairCandidates[0].requiredKnowledgeSections;
        const env={PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'};
        const native=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),'--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json',...(rawWhitespace?['--raw-string-whitespace','enabled']:[]),input.prompt],{cwd:root,env,encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
        fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);
        if(native.status!==0)throw new Error(native.stderr+'\n'+native.stdout);
        return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const suffix=rawWhitespace?'\n\tline':'';const candidate={name:'a.md',kind:'project',classification:'private',content:header+'Old claim'+suffix+purpose,evidence:[{index:0,quote:'Correct claim'+suffix}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]};
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Correct claim'+suffix}]},existingMemories:[]}});
      console.log(JSON.stringify({result,sections,expected:header+'Correct claim'+suffix+purpose,wroteMemory:fs.existsSync(path.join(root,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('RAW_WHITESPACE', str(raw_whitespace).lower()).replace('INSIDE_COLON', json.dumps(inside_colon)))
    assert result['result']['outcome'] == 'repaired', str(result['result'])['result']
    assert result['result']['plan']['newMemories'][0]['content'] == result['expected']
    assert result['sections'] == ['Why', 'How to apply']
    assert not result['wroteMemory']


def test_empty_or_sensitive_amendments_do_not_acknowledge_correction(tmp_path) -> None:
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let output;let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,stderr:'',text:JSON.stringify(output),cancelled:false}}}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[a]};
      const input={identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],outputDir:ROOT,semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}};
      output={kind:'incremental-memory-amendment',version:1,...identity,replacements:[]};
      const empty=await repairIncrementalMemoryPlan(input);
      output.replacements=[{candidateId:semanticMemoryRepairCandidates(original)[0].candidateId,content:'api_key=sk-'+'x'.repeat(40),evidence:a.evidence}];
      await repairIncrementalMemoryPlan(input);
      const saved=JSON.parse(fs.readFileSync(path.join(input.outputDir,'repair-response.json'),'utf8'));
      console.log(JSON.stringify({empty,saved,calls}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['empty']['failureKind'] == 'no-correction'
    assert 'plan' not in result['empty']
    assert result['saved']['sensitive']
    assert 'output' not in result['saved']
    assert result['calls'] == 2


def test_real_raw_json_whitespace_repair_keeps_content_and_parent_bindings(tmp_path) -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt;
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-amendment-raw-whitespace.json','utf8'));
      const original=fixture.files['semantic-rejected-plan.json'].value,snapshot=fixture.files['snapshot.json'].value,raw=fixture.files['repair-response.json'].value.output;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:raw,cancelled:false};}}));
      const {repairIncrementalMemoryPlan,candidateCitationProblems}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {containsSensitiveMemoryMaterial,sha256Digest}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['description held'],selectedNames:[],repairableNames:original.newMemories.map(x=>x.name),repairableFields:Object.fromEntries(original.newMemories.map(x=>[x.name,['description']])),semanticContext:{frozenEvidence:snapshot,existingMemories:[]},outputDir:process.env.PROBE_DIR});
      const originalResponse=JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-response.json','utf8'));
      const diagnosticFile=process.env.PROBE_DIR+'/repair-json-whitespace.json';
      const diagnostic=fs.existsSync(diagnosticFile)?JSON.parse(fs.readFileSync(diagnosticFile,'utf8')):null;
      console.log(JSON.stringify({result,original,rawPreserved:originalResponse.output===raw,diagnostic,prompt,sensitive:containsSensitiveMemoryMaterial(JSON.stringify(fixture)),sourceHash:sha256Digest(raw),citations:result.plan?candidateCitationProblems(snapshot,result.plan.newMemories):null}));
    ''', env={'PROBE_DIR': str(tmp_path)})
    assert result['result']['outcome'] == 'repaired', str(result['result'])['result']
    assert result['rawPreserved'] and not result['sensitive']
    assert result['sourceHash'] == '6e257b548cd02902a26fdcb52924af2086f289b87ff209a51285a74853f84e55'
    assert result['citations'] == []
    assert result['result']['plan']['operations'] == result['original']['operations']
    old, new = result['original']['newMemories'][0], result['result']['plan']['newMemories'][0]
    assert old['name'] == new['name'] and old['classification'] == new['classification']
    assert old['content'].split('\n---\n', 1)[1] == new['content'].split('\n---\n', 1)[1]
    assert result['diagnostic']['originalTextSha256'] == result['sourceHash']
    assert result['diagnostic']['serializationOnly'] and not result['diagnostic']['semanticAcceptance']
    assert 'Escape newline' in result['prompt']


def test_sensitive_normalized_amendment_keeps_hash_diagnostic_without_original_text(tmp_path):
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const item={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[item]};
      let output;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({exitCode:0,stderr:'',cancelled:false,text:output})}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      output=JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:semanticMemoryRepairCandidates(original)[0].candidateId,content:'header\napi_key=sk-'+'x'.repeat(40),evidence:item.evidence}]}).replace('\\n','\n');
      await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]},outputDir:process.env.PROBE_DIR});
      const saved=JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-response.json','utf8'));
      const diagnostic=JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-json-whitespace.json','utf8'));
      console.log(JSON.stringify({saved,diagnostic}));
    ''', env={'PROBE_DIR': str(tmp_path)})
    assert result['saved']['sensitive'] and 'output' not in result['saved']
    assert result['diagnostic']['counts']['newline'] == 1
    assert result['diagnostic']['serializationOnly'] and not result['diagnostic']['semanticAcceptance']


def test_real_content_patch_reuses_only_bound_original_citations(tmp_path):
    # Given the complete real V49 failure and a body-only repair grant, When
    # the semantic worker omits unchanged citations, Then retain those exact
    # verified sources without approval, metadata drift or a second model call.
    value=isolated_run_bun(r'''
      import fs from 'node:fs';import {mock} from 'bun:test';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-inheritance.json').json();
      const kit=await import('./packages/kit/src/index.ts');let calls=0,prompt,args;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        calls++;prompt=input.prompt;args=input.extraArgs;return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify(f.response)};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {resolveMemoryPlanCitations}=await import('./packages/continual-learning/extensions/memory-citation-locations.ts');
      const original=f.original,before=JSON.stringify(f),identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const name=original.operations[0].name,originalResolved=resolveMemoryPlanCitations(original,f.snapshot);
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,selectedNames:[name],repairableNames:[name],repairableFields:{[name]:['body']},errors:['counterevidence held'],
        semanticContext:{frozenEvidence:f.snapshot,existingMemories:[]},outputDir:process.env.PROBE_DIR});
      const content=result.plan?.operations[0].content;
      console.log(JSON.stringify({outcome:result.outcome,calls,unchanged:before===JSON.stringify(f),originalDescription:original.operations[0].content.split('\n').find(x=>x.startsWith('description:')),
        correctedDescription:content?.split('\n').find(x=>x.startsWith('description:')),bodyChanged:!!content&&content!==original.operations[0].content,
        evidenceUnchanged:JSON.stringify(result.plan?.operations[0].evidence)===JSON.stringify(originalResolved.operations[0].evidence),
        rawOutputUnchanged:JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/repair-response.json','utf8')).output===JSON.stringify(f.response),
        sourceContract:JSON.parse(prompt.split('\n').at(-1)).repairCandidates[0].reuseOriginalEvidence,
        outputKind:args[args.indexOf('--learning-output-schema')+1],proof:JSON.parse(fs.readFileSync(process.env.PROBE_DIR+'/semantic-repair-source-inheritance.json','utf8'))}));
    ''', env={'PROBE_DIR':str(tmp_path)})
    assert value['outcome']=='repaired'
    assert value['calls']==1 and value['unchanged'] and value['bodyChanged']
    assert value['originalDescription']==value['correctedDescription']
    assert value['evidenceUnchanged'] and value['rawOutputUnchanged']
    assert value['sourceContract'] is True
    assert value['outputKind']=='memory-semantic-amendment'
    assert value['proof']['originalCitationsOnly'] and not value['proof']['semanticAcceptance']


def test_content_patch_source_inheritance_rejects_unbound_invalid_or_empty_changes():
    rows=isolated_run_bun(r'''
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-inheritance.json').json();
      const {bindSemanticMemoryAmendment,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const modes=['valid','no-context','no-fields','tampered-snapshot','empty-evidence','null-evidence','undefined-evidence','missing-content','unchanged-content','locked-only','foreign-id','missing-identity','missing-original-evidence','invalid-original-quote'];
      const rows=[];for(const mode of modes){
        const original=structuredClone(f.original),response=structuredClone(f.response),snapshot=structuredClone(f.snapshot),name=original.operations[0].name;
        const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
        if(mode==='tampered-snapshot')snapshot.entries[0].unboundChange=true;
        if(mode==='empty-evidence')response.replacements[0].evidence=[];
        if(mode==='null-evidence')response.replacements[0].evidence=null;
        if(mode==='undefined-evidence')response.replacements[0].evidence=undefined;
        if(mode==='missing-content')delete response.replacements[0].content;
        if(mode==='unchanged-content')response.replacements[0].content=original.operations[0].content;
        if(mode==='locked-only')response.replacements[0].content=original.operations[0].content.replace(/^description:.*$/m,'description: Changed locked description');
        if(mode==='foreign-id')response.replacements[0].candidateId='foreign';
        if(mode==='missing-identity')delete response.snapshotDigest;
        // A source change must not retain the stale candidate-bound identity.
        if(mode==='missing-original-evidence')delete original.operations[0].evidence;
        if(mode==='invalid-original-quote')original.operations[0].evidence=[{index:49,quote:'Not in the original source'}];
        if(mode==='missing-original-evidence'||mode==='invalid-original-quote')response.replacements[0].candidateId=semanticMemoryRepairCandidates(original)[0].candidateId;
        const before=JSON.stringify({original,response,snapshot});let accepted=false;
        try{bindSemanticMemoryAmendment(original,response,identity,[name],mode==='no-context'?undefined:{frozenEvidence:snapshot,repairableFields:mode==='no-fields'?{}:{[name]:['body']}});accepted=true;}catch{}
        rows.push({mode,accepted,unchanged:before===JSON.stringify({original,response,snapshot})});
      }console.log(JSON.stringify(rows));
    ''')
    assert rows[0]['accepted']
    assert all(not row['accepted'] for row in rows[1:])
    assert all(row['unchanged'] for row in rows)


def test_actual_pi_semantic_content_patch_retains_real_original_sources():
    value=isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import{repairIncrementalMemoryPlan}from'./packages/continual-learning/extensions/inject-memory.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-repair-source-inheritance.json').json();
      const agent=process.env.PI_CODING_AGENT_DIR;let calls=0,tools;
      const server=Bun.serve({hostname:'127.0.0.1',port:0,fetch:async request=>{
        calls++;const wire=await request.json();tools=wire.tools;
        const reply=JSON.stringify(f.response),chunk=(delta,finish_reason)=>'data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',model:'offline',choices:[{index:0,delta,finish_reason}]})+'\n\n';
        return new Response(chunk({role:'assistant',content:reply},null)+chunk({},'stop')+'data: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}});
      }});
      fs.writeFileSync(path.join(agent,'models.json'),JSON.stringify({providers:{fixture:{baseUrl:`http://127.0.0.1:${server.port}/v1`,api:'openai-completions',apiKey:'offline',models:[{id:'offline',name:'offline',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:4096,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
      fs.writeFileSync(path.join(agent,'settings.json'),JSON.stringify({packages:[],extensions:[],skills:[],retry:{enabled:false}}));
      process.env.PI_OFFLINE='1';process.argv[1]=fs.realpathSync('./node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');process.execPath=Bun.which('node');
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,f.original[k]])),name=f.original.operations[0].name,before=JSON.stringify(f);
      try{const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:f.original,selectedNames:[name],repairableNames:[name],repairableFields:{[name]:['body']},errors:['held'],model:'fixture/offline',semanticContext:{frozenEvidence:f.snapshot,existingMemories:[]}});
        console.log(JSON.stringify({outcome:result.outcome,calls,tools:tools?.length??0,unchanged:before===JSON.stringify(f),sourceCount:result.plan?.operations[0].evidence.length,
          piVersion:JSON.parse(fs.readFileSync('./node_modules/@earendil-works/pi-coding-agent/package.json','utf8')).version,externalRequests:0}));
      }finally{server.stop(true)}
    ''',timeout=45)
    assert value=={'outcome':'repaired','calls':1,'tools':0,'unchanged':True,'sourceCount':3,'piVersion':'1.3.0','externalRequests':0}


@pytest.mark.parametrize("mode", ["no-entry", "no-entry-final-held", "no-entry-required"])
def test_parent_no_entry_requires_final_set_review_before_later_phases(mode):
    from pathlib import Path
    from support import run_bun_script
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'memory-apply', env={'CL_JEV_FIXTURE': mode, 'CL_LATER_AFTER_MEMORY': '1'})
    assert result['semanticRepairs'] == 1
    receipt = result.get('registryReceipt') or next(run['receipt'] for run in result['runs'] if run.get('receipt'))
    attempts = receipt['attempts']
    if mode == 'no-entry':
        assert any(a.get('declinedOperations') == 1 and a['operations'] == 0 for a in attempts)
        assert result['reviewWireCalls'] == 2
        assert 'harness' in result['planners'] and 'agents' in result['planners']
        assert any(a['outcome'] == 'declined' for a in attempts)
    else:
        assert not any(a.get('declinedOperations') for a in attempts)
        assert 'harness' not in result['planners'] and 'agents' not in result['planners']
        assert not result['receiptComplete']
    assert 'concise.md' not in result['privateFiles'] and 'concise.md' not in result['publicFiles']


def test_atomic_knowledge_correction_materializes_body_and_sources_together():
    """Given V121's new dependency, When corrected, Then its source selection travels with that body unit."""
    result = isolated_run_bun(r'''
      import {materializeMemoryKnowledge,materializeMemoryDescription} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const original='---\nname: failure\ndescription: Existing observation\ntype: project\n---\nOld body.';
      const source={contextEnabled:true,entries:[{role:'toolResult',content:'const second = deferred();\nconst job = second.promise;\nassert.equal(reported, false);\nsecond.resolve();'},{role:'assistant',content:'An invented explanation.'}]};
      const knowledge={sourceCitations:[{ref:'e0.b0.l1',endRef:'e0.b0.l2'},{ref:'e0.b0.l3',endRef:'e0.b0.l4'}],units:[{text:'**Condition**: Follow-up work depends on second.promise.',citationIndexes:[0]},{text:'**Order**: second.resolve() occurs after the assertion.',citationIndexes:[1]}]};
      const good=materializeMemoryKnowledge(original,knowledge,source);
      const denied=[];for(const k of [[],{sourceCitations:[],units:knowledge.units},{...knowledge,units:[]},{...knowledge,units:[{text:'new relation',citationIndexes:[]}]},{...knowledge,units:[{text:'new relation',citationIndexes:[2]}]},{...knowledge,units:[{text:'new relation',citationIndexes:[0,0]}]},{...knowledge,sourceCitations:[{ref:'e1.b0.l1'}]},{...knowledge,sourceCitations:[{ref:'e0.b0.l99'}]},{...knowledge,sourceCitations:Array(9).fill({ref:'e0.b0.l1'})},{...knowledge,units:[{text:'new relation',citationIndexes:[0],content:'hidden'}]}]){try{materializeMemoryKnowledge(original,k,source);denied.push(false)}catch{denied.push(true)}}
      const formatted=original.replaceAll('\n','\r\n')+'\r\n\r\n    code indentation\r\n';
      const described=materializeMemoryDescription(formatted,'Revised discovery');
      const invalidDescriptions=[];for(const value of ['',null,42,'foreign\nname: injected']){try{materializeMemoryDescription(formatted,value);invalidDescriptions.push(false)}catch{invalidDescriptions.push(true)}}
      console.log(JSON.stringify({good,denied,original,formatted,described,invalidDescriptions}));
    ''')
    assert all(result['denied'])
    assert result['good']['content'].endswith('second.resolve() occurs after the assertion.')
    assert 'second.promise' in result['good']['evidence'][0]['quote']
    assert 'second.resolve()' in result['good']['evidence'][1]['quote']
    assert 'Old body.' not in result['good']['content']
    assert result['good']['content'].split('---\n')[1] == result['original'].split('---\n')[1]
    assert result['described'] == result['formatted'].replace('description: Existing observation', 'description: Revised discovery')
    assert all(result['invalidDescriptions'])


def test_parent_atomic_repair_rejects_body_with_detached_stale_citations():
    # Given atomic output framing, When the final repair worker is launched,
    # Then it retains the shared knowledge contract once as well as citations.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let next,prompt,args;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async i=>{prompt=i.prompt;args=i.extraArgs;return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false,usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:.01},usageLedger:{complete:true}}}}));
      const {MEMORY_KNOWLEDGE_GUIDANCE}=await import('./packages/continual-learning/extensions/planner-prompts.ts');
      const {sha256Digest}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const frozen={contextEnabled:true,runId:'r',scopeKey:'s',entries:[{role:'toolResult',content:'A source failure.\nFollow-up depends on second.promise.\nRelease occurs after the assertion.'}]};
      const digest=sha256Digest(JSON.stringify(frozen,null,2)+'\n');const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:digest,snapshotDigest:digest};
      const content='---\nname: failure\ndescription: Source failure\ntype: project\n---\nA source failure.';
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'failure.md',kind:'project',classification:'safe',content,evidence:[{ref:'e0.b0.l1'}]}]};
      const candidate=semanticMemoryRepairCandidates(original)[0];const patch={candidateId:candidate.candidateId,knowledge:{sourceCitations:[{ref:'e0.b0.l1'},{ref:'e0.b0.l2',endRef:'e0.b0.l3'}],units:[{text:'A source failure.',citationIndexes:[0]},{text:'Follow-up depends on second.promise. Release occurs after the assertion.',citationIndexes:[1]}]}};
      const envelope={kind:'incremental-memory-amendment',version:1,...identity,replacements:[patch]};
      const input={identity,rejectedPlan:original,selectedNames:[],repairableNames:['failure.md'],repairableFields:{'failure.md':['body']},atomicBodyEvidence:true,errors:['held'],semanticContext:{frozenEvidence:frozen,existingMemories:[]}};
      next=envelope;const good=await repairIncrementalMemoryPlan(input);const payload=JSON.parse(prompt.split('\n').at(-1));
      const knowledgeContractCount=prompt.split(MEMORY_KNOWLEDGE_GUIDANCE).length-1;
      next={...envelope,replacements:[{candidateId:candidate.candidateId,content:content+'\nNew unsupported relationship.',evidence:[{ref:'e0.b0.l1'}]}]};const detached=await repairIncrementalMemoryPlan(input);
      next={...original,newMemories:[{...original.newMemories[0],content:content+'\nNew relationship.'}]};const regenerated=await repairIncrementalMemoryPlan(input);
      next=structuredClone(envelope);next.replacements[0].knowledge.units[1].citationIndexes=[];const uncited=await repairIncrementalMemoryPlan(input);
      next=structuredClone(envelope);next.replacements[0].knowledge.sourceCitations=Array(9).fill({ref:'e0.b0.l1'});const overflow=await repairIncrementalMemoryPlan(input);
      next={...envelope,replacements:[{candidateId:candidate.candidateId,description:'Observed source failure',evidence:[{ref:'e0.b0.l1'}]}]};
      const descriptionOnly=await repairIncrementalMemoryPlan({...input,repairableFields:{'failure.md':['description']}});
      const unauthorizedDescription=await repairIncrementalMemoryPlan(input);
      next.replacements[0].content=content+'\nDifferent body.';
      const ambiguousDescription=await repairIncrementalMemoryPlan({...input,repairableFields:{'failure.md':['description']}});
      console.log(JSON.stringify({good,detached,regenerated,uncited,overflow,descriptionOnly,unauthorizedDescription,ambiguousDescription,content,payload,args,knowledgeContractCount}));
    ''')
    assert result['knowledgeContractCount'] == 1
    assert result['good']['outcome'] == 'repaired'
    assert 'second.promise' in result['good']['plan']['newMemories'][0]['content']
    assert any('Release occurs after' in row['quote'] for row in result['good']['plan']['newMemories'][0]['evidence'])
    assert all(result[k]['outcome'] == 'failed' and result[k]['usage']['cost'] == .01 for k in ('detached', 'regenerated', 'uncited', 'overflow'))
    assert result['payload']['atomicKnowledgeContract']['oldCitationsInherited'] is False
    assert '--learning-atomic-knowledge' in result['args']

    assert result['overflow']['failureKind'] == 'citation' and '1..8' in result['overflow']['error']
    assert result['payload']['atomicKnowledgeContract']['version'] == 2
    assert result['payload']['atomicKnowledgeContract']['maximumSourceCitationsPerCandidate'] == 8
    assert result['descriptionOnly']['outcome'] == 'repaired', result['descriptionOnly']
    corrected = result['descriptionOnly']['plan']['newMemories'][0]
    assert corrected['content'] == result['content'].replace('description: Source failure', 'description: Observed source failure')
    assert corrected['evidence'] == [{'index': 0, 'quote': 'A source failure.'}]
    assert result['descriptionOnly']['usage']['cost'] == .01
    assert all(result[k]['outcome'] == 'failed' and result[k]['failureKind'] == 'intent'
               and result[k]['usage']['cost'] == .01 for k in ('unauthorizedDescription', 'ambiguousDescription'))

def test_atomic_retained_body_correction_selects_native_worker_protocol():
    # Given a retained body contradicted by source, When its atomic repair is
    # prepared, Then the actual native Qwen hook accepts the retained protocol.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerStructuredOutput:true}));
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let args,wire;
      const {sha256Digest}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const frozen={contextEnabled:true,runId:'r',scopeKey:'s',scopeDigest:'d',entries:[{role:'toolResult',content:'Correct source contract.'}]};
      const digest=sha256Digest(JSON.stringify(frozen,null,2)+'\n'),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:digest,snapshotDigest:digest};
      const header='---\nname: Example\ndescription: Source contract.\ntype: project\n---\n';
      const prior={name:'a.md',classification:'private',type:'project',content:header+'Old source contract.'};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        args=input.extraArgs;const flags=new Map();for(let n=0;n<args.length-1;n++)if(args[n].startsWith('--'))flags.set(args[n].slice(2),args[n+1]);
        const extension=(await import('./packages/continual-learning/extensions/planner-json-output.ts')).default;let hook;
        extension({registerFlag:()=>{},getFlag:n=>flags.get(n),on:(name,fn)=>{if(name==='before_provider_request')hook=fn},getActiveTools:()=>[]});
        wire=hook({payload:{messages:[{role:'user',content:'Return JSON.'}]}},{model:{api:'openai-completions',id:'bailian/qwen3.8-flash'}});
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'a.md',kind:'rewrite',classification:'private',knowledge:{sourceCitations:[{ref:'e0.b0.l1'}],units:[{text:'Correct source contract.',citationIndexes:[0]}]}}],newMemories:[]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:{kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]},selectedNames:['a.md'],retainedRepairNames:['a.md'],requiredTextChanges:{'a.md':['body']},atomicBodyEvidence:true,errors:['contradicted body'],semanticContext:{frozenEvidence:frozen,existingMemories:[prior]}});
      console.log(JSON.stringify({result,args,wire}));
    ''')
    assert result['args'][result['args'].index('--learning-output-schema') + 1] == 'memory-retained-amendment'
    assert result['result']['outcome'] == 'repaired', str(result['result'])
    assert result['result']['plan']['operations'][0]['content'].endswith('Correct source contract.')
    assert result['wire']['response_format']['json_schema']['name'] == 'memory_retained_amendment'
