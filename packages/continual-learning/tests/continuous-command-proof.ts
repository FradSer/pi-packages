/** Study provenance only. Callers must still verify history, corpus, safety,
 * semantic approval and the frozen exclusive owner's invocation authority. */
import {createHash} from 'node:crypto';
import path from 'node:path';
import {isDeepStrictEqual} from 'node:util';
import {currentTaskSlice,requestedMemoryTaskSlice} from '../extensions/incremental-learning';
import {reviewedSourceExtension} from '../extensions/learning-replay-feedback';
import {formatPlannerFileRead} from '../extensions/planner-read-scope';
import {isLearningPipelineReceipt} from '../extensions/learning-efficiency';
import {backlogIdentity} from '../extensions/learning-backlog';
import {ruleRevision} from '../extensions/guardrail-engine';

const hash=(text:string)=>createHash('sha256').update(text).digest('hex');
const exact=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
const record=(value:unknown):value is Record<string,any>=>value!==null && typeof value==='object' && !Array.isArray(value);
const sameUsage=(a:any,b:any)=>['input','output','cacheRead','cacheWrite','totalTokens','cost'].every(key=>
 typeof a?.[key]==='number' && Number.isFinite(a[key]) && a[key]>=0 && a[key]===b?.[key]);

function nativeRows(text:string):Record<string,any>[] {
 if(typeof text!=='string' || !text.endsWith('\n'))throw Error('Incomplete native JSONL');
 const rows=text.slice(0,-1).split('\n').map(line=>JSON.parse(line));
 const header=rows[0];
 if(!record(header) || header.type!=='session' || typeof header.id!=='string' || !header.id)throw Error('Missing native session');
 const ids=new Set<string>();let parent:string|null=null;
 for(const row of rows.slice(1)){
  if(!record(row) || typeof row.id!=='string' || !row.id || ids.has(row.id)
    || row.type==='session' || row.parentId!==parent)throw Error('Incomplete or ambiguous native branch');
  ids.add(row.id);parent=row.id;
 }
 return rows;
}

/** Bind a fresh no-tools user task to one newly auto-owned rule. The frozen
 * owner, production semantic gates and later execution evidence remain required.
 * This is not permission to add arbitrary receipt owners to a replay chain. */
export function automaticHarnessPolicyProof(input:any,prior:any,current:any):Record<string,unknown> {
 const base={origin:'automatic-user-policy',mutationAuthority:false,learningBenefitEstablished:false};
 try{
  if(input?.kind!=='automatic-harness-policy-review' || input.version!==1)throw Error('Unknown policy proof');
  const {owner,completion,receipt,reviewManifest:manifest,usageLedger,postReceipt:post}=input;
  if(!record(owner) || owner.kind!=='native-automatic-harness-policy' || owner.version!==1
    || !record(completion) || completion.ownerDigest!==hash(JSON.stringify(owner))
    || owner.piVersion!=='1.3.0' || completion.exitCode!==0 || completion.timedOut!==false || completion.cancelled!==false
    || !Number.isSafeInteger(owner.startedAt) || !Number.isSafeInteger(completion.settledAt) || completion.settledAt<owner.startedAt
    || !path.isAbsolute(owner.cwd) || !path.isAbsolute(owner.agentDir) || !path.isAbsolute(owner.sessionPath)
    || !owner.sessionPath.startsWith(path.join(owner.agentDir,'sessions')+path.sep)
    || typeof owner.prompt!=='string' || !owner.prompt.trim()
    || !Array.isArray(owner.argv) || owner.argv.some((arg:any)=>typeof arg!=='string')
    || owner.argv.filter((arg:string)=>arg==='--no-tools').length!==1 || owner.argv.includes('--tools')
    || owner.argv.filter((arg:string)=>arg==='--session').length!==1
    || owner.argv[owner.argv.indexOf('--session')+1]!==owner.sessionPath || owner.argv.at(-1)!==owner.prompt
    || !owner.argv.includes('--print') || owner.argv.filter((arg:string)=>arg==='--mode').length!==1
    || owner.argv[owner.argv.indexOf('--mode')+1]!=='json')throw Error('Unbound policy invocation');
  if(!record(owner.sourceFiles) || !Object.keys(owner.sourceFiles).length || !isDeepStrictEqual(owner.sourceFiles,completion.sourceFiles)
    || Object.entries(owner.sourceFiles).some(([name,value])=>!name || path.isAbsolute(name) || name.split(/[\\/]/).some(part=>!part || part==='.' || part==='..')
      || !record(value) || !/^[a-f0-9]{64}$/.test(value.sha256) || !Number.isSafeInteger(value.mode) || value.mode<0 || value.mode>0o777
      || !Number.isSafeInteger(value.size) || value.size<0))
   throw Error('Policy source changed or is incomplete');
  const rows=nativeRows(input.nativeSession);
  if(rows[0].cwd!==owner.cwd || hash(input.nativeSession)!==completion.sessionDigest || hash(input.stdout)!==completion.stdoutDigest)
   throw Error('Changed policy session');
  const delivered=rows.filter(row=>row.type==='custom_message' && row.customType==='continual-learning-result');
  const stdoutRows=input.stdout.trim().split('\n').map((line:string)=>JSON.parse(line));
  const emitted=stdoutRows.filter((row:any)=>row.type==='message_end' && row.message?.customType==='continual-learning-result');
  if(!isLearningPipelineReceipt(receipt) || receipt.mode!=='automatic' || receipt.operations!==1
    || receipt.screen.memory!==false || receipt.screen.harness!==true || receipt.screen.agents!==false
    || receipt.attempts.some(attempt=>attempt.pendingOperations || attempt.operations>0 && (attempt.phase!=='harness' || attempt.outcome!=='applied'))
    || receipt.attempts.filter(attempt=>attempt.phase==='harness').at(-1)?.outcome!=='applied'
    || delivered.length!==1 || !isDeepStrictEqual(delivered[0].details,receipt)
    || emitted.length!==1 || !isDeepStrictEqual(emitted[0].message.details,receipt))throw Error('Missing unique applied automatic receipt');
  const prefix=rows.slice(1,rows.indexOf(delivered[0]));
  const users=rows.filter(row=>row.message?.role==='user');
  const assistants=rows.filter(row=>row.message?.role==='assistant');
  const completed=stdoutRows.filter((row:any)=>row.type==='message_end' && row.message?.role==='assistant');
  if(users.length!==1 || !exact(users[0].message.content,[{type:'text',text:owner.prompt}]) || !assistants.length
    || assistants.length!==completed.length || assistants.some(row=>completed.filter((event:any)=>isDeepStrictEqual(event.message,row.message)).length!==1)
    || stdoutRows.some((row:any)=>['tool_execution_start','tool_execution_end'].includes(row.type))
    || rows.some(row=>row.message?.role==='toolResult' || row.message?.role==='assistant'
      && (row.message.stopReason!=='stop' || row.message.content?.some((part:any)=>part.type==='toolCall'))))
   throw Error('Policy is not a distinct no-tools user task');
  const task=currentTaskSlice(prefix),range=receipt.input?.backlogRange;
  const start=prefix.indexOf(users[0]);
  if(task.omittedEntries || task.omittedEvidenceEntries || !range || range.from!==start || range.to!==prefix.length-1
    || range.digest!==hash(JSON.stringify(task)) || receipt.input?.source!=='current-session' || receipt.input.entryCount!==prefix.length
    || receipt.input.backlogId!==backlogIdentity(manifest.scopeKey,{sessionFile:owner.sessionPath,...range}))throw Error('Unbound actual policy task slice');
  const snapshot=JSON.parse(input.snapshotText);
  const generation=receipt.attempts.filter(attempt=>attempt.phase==='harness' && attempt.outcome==='applied' && attempt.operations===1);
  const ledgerIdPattern=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
  if(!record(manifest) || manifest.cwd!==owner.cwd || manifest.runDir!==path.join(owner.agentDir,'memory','runs',manifest.scopeKey,manifest.runId)
    || manifest.snapshotPath!==path.join(manifest.runDir,'snapshot.json') || manifest.snapshotDigest!==hash(input.snapshotText)
    || snapshot.runId!==manifest.runId || snapshot.scopeKey!==manifest.scopeKey || !isDeepStrictEqual(snapshot.entries,task.entries)
    || !record(usageLedger) || typeof usageLedger.complete!=='boolean' || !ledgerIdPattern.test(usageLedger.ledgerId)
    || generation.length!==1 || ![0,1].includes(generation[0].attempt)
    || generation[0].usageLedgerId!==usageLedger.ledgerId || generation[0].usageComplete!==usageLedger.complete
    || !sameUsage(generation[0].usage,usageLedger.knownUsage)
    || input.usageLedgerPath!==path.join(manifest.runDir,generation[0].attempt===0?'harness-task-usage.json':`harness-repair-usage-${usageLedger.ledgerId}.json`)
    || post?.kind!=='harness-consolidation-receipt' || post.phase!=='post' || post.runId!==manifest.runId
    || post.scopeDigest!==manifest.scopeDigest || post.snapshotDigest!==manifest.snapshotDigest
    || post.targetFile!==path.join(owner.cwd,'.pi','harness.json'))throw Error('Unbound policy generation or cost');
  if(generation[0].attempt===1){
   const initial=input.initialUsageLedger;
   if(!record(initial) || !ledgerIdPattern.test(initial.ledgerId) || initial.ledgerId===usageLedger.ledgerId
     || typeof initial.complete!=='boolean' || input.initialUsageLedgerPath!==path.join(manifest.runDir,'harness-task-usage.json')
     || receipt.attempts.filter(attempt=>attempt.phase==='harness' && attempt.attempt===0 && attempt.usageLedgerId===initial.ledgerId
       && attempt.usageComplete===initial.complete && sameUsage(attempt.usage,initial.knownUsage)).length!==1)
    throw Error('Missing original policy generation cost');
  }
  for(const state of [prior,current]){
   if(!record(state) || !record(state.surfaceSnapshots) || !Array.isArray(state.memoryEntries) || !Array.isArray(state.history)
     || !Array.isArray(state.receipts) || !Array.isArray(state.attempts) || !record(state.completedBacklog)
     || state.pendingLearningJobs!==0 || state.backlogStatus?.pending!==0
     || ['error','malformed','unlearnable','unscoped'].some(key=>state.backlogStatus[key]))throw Error('Incomplete policy endpoint');
  }
  const freshAttempts=[...current.attempts];
  for(const attempt of prior.attempts){
   const index=freshAttempts.findIndex((value:any)=>isDeepStrictEqual(attempt,value));
   if(index<0)throw Error('Policy lost a prior attempt');
   freshAttempts.splice(index,1);
  }
  if(freshAttempts.length!==1 || freshAttempts[0].outcome!=='completed'
    || !isDeepStrictEqual(freshAttempts[0].receipt,receipt) || freshAttempts[0].receiptDigest!==hash(JSON.stringify(receipt))
    || !isDeepStrictEqual(freshAttempts[0].sourceBinding,{source:'current-session',entryCount:prefix.length}))
   throw Error('Missing actual current-task completion record');
  if(!isDeepStrictEqual(prior.memoryEntries,current.memoryEntries)
    || prior.receipts.some((row:any)=>!current.receipts.some((next:any)=>isDeepStrictEqual(row,next)))
    || prior.receipts.some((row:any)=>row.batchId===receipt.batchId)
    || current.receipts.length!==prior.receipts.length+1 || current.receipts.filter((row:any)=>isDeepStrictEqual(row,receipt)).length!==1
    || Object.entries(prior.completedBacklog).some(([key,value])=>current.completedBacklog[key]!==value)
    || Object.keys(current.completedBacklog).length!==Object.keys(prior.completedBacklog).length+1
    || current.completedBacklog[receipt.input!.backlogId!]!==hash(JSON.stringify(receipt)))throw Error('Policy lost prior learning or costs');
  const old=new Map(prior.history.map((row:any)=>[row.id,row]));
  if(old.size!==prior.history.length || new Set(current.history.map((row:any)=>row.id)).size!==current.history.length
    || prior.history.some((row:any)=>!current.history.some((next:any)=>isDeepStrictEqual(row,next))))throw Error('Changed prior policy history');
  const fresh=current.history.filter((row:any)=>!old.has(row.id));
  if(!fresh.length || fresh.some((row:any)=>row.batchId!==receipt.batchId || row.phase!=='harness'
    || !['applied','proposed','abandoned'].includes(row.status)))throw Error('Unowned policy history');
  const applied=fresh.filter((row:any)=>row.status==='applied');
  const key='project/.pi/harness.json',before=prior.surfaceSnapshots[key]??null,after=current.surfaceSnapshots[key];
  if(applied.length!==1 || applied[0].changes?.length!==1 || applied[0].cwd!==owner.cwd || applied[0].agentDir!==owner.agentDir
    || applied[0].changes[0].target?.root!=='project' || applied[0].changes[0].target.name!=='.pi/harness.json'
    || !isDeepStrictEqual(applied[0].changes[0].before,before) || !isDeepStrictEqual(applied[0].changes[0].after,after)
    || post.digestBefore!==(before?.digest??null) || post.digestAfter!==after?.digest)throw Error('Missing exact policy physical history');
  for(const name of new Set([...Object.keys(prior.surfaceSnapshots),...Object.keys(current.surfaceSnapshots)])){
   if(name!==key && !isDeepStrictEqual(prior.surfaceSnapshots[name],current.surfaceSnapshots[name]))throw Error('Policy changed an unrelated surface');
  }
  const decode=(physical:any)=>{
   if(!record(physical) || typeof physical.bytes!=='string')throw Error('Missing policy bytes');
   const bytes=Buffer.from(physical.bytes,'base64');
   if(bytes.toString('base64')!==physical.bytes || hash(bytes.toString('utf8'))!==physical.digest
     || !Number.isSafeInteger(physical.mode) || physical.mode<0 || physical.mode>0o777
     || typeof physical.revision!=='string' || !/^\d+:\d+:\d+:-?\d+:-?\d+$/.test(physical.revision)
     || Number(physical.revision.split(':')[2])!==bytes.length)throw Error('Invalid policy physical revision');
   return JSON.parse(bytes.toString('utf8'));
  };
  const previous=before===null?{rules:[]}:decode(before),next=decode(after);
  if(!Array.isArray(previous.rules) || !Array.isArray(next.rules) || Object.keys(previous.learnedRules??{}).length
    || !record(next.learnedRules) || Object.keys(next.learnedRules).length!==1 || next.rules.length!==previous.rules.length+1
    || previous.rules.some((rule:any)=>next.rules.filter((value:any)=>isDeepStrictEqual(rule,value)).length!==1))throw Error('Policy replaced prior rules');
  const added=next.rules.filter((rule:any)=>!previous.rules.some((value:any)=>value.id===rule.id));
  const withoutRules=({rules,learnedRules,...rest}:any)=>rest;
  if(added.length!==1 || typeof added[0].id!=='string' || !added[0].id
    || next.learnedRules[added[0].id]?.origin!=='consolidation' || next.learnedRules[added[0].id].revision!==ruleRevision(added[0])
    || !isDeepStrictEqual(withoutRules(previous),withoutRules(next)))throw Error('Missing new consolidation-owned revision');
  return {...base,ready:true,batchId:receipt.batchId,ruleId:added[0].id,ruleRevision:ruleRevision(added[0]),
   receiptDigest:hash(JSON.stringify(receipt)),sessionDigest:completion.sessionDigest,changedPaths:[key]};
 }catch(error){return {...base,ready:false,reason:error instanceof Error?error.message:'Invalid automatic policy'};}
}

/** This discriminated adapter never calls a model, writes state, fabricates a
 * replay attempt, or converts provenance into semantic/mutation authority. */
export function commandMemorySourceProof(input:any):Record<string,unknown> {
 const base={origin:'explicit-memory-command',mutationAuthority:false,initializationApproved:false,learningBenefitEstablished:false};
 try{
  if(input?.kind!=='explicit-command-source-review' || input.version!==1)throw Error('Unknown command proof');
  const {owner,completion,receipt,plan,reviewManifest:manifest,sourceAudit,usageLedger}=input;
  if(!record(owner) || owner.kind!=='native-memory-command' || owner.version!==1
    || !record(completion) || completion.ownerDigest!==hash(JSON.stringify(owner))
    || completion.exitCode!==0 || completion.cancelled!==false || completion.timedOut!==false
    || !Number.isSafeInteger(owner.startedAt) || !Number.isSafeInteger(completion.settledAt)
    || completion.settledAt<owner.startedAt || owner.piVersion!=='1.3.0'
    || !Array.isArray(owner.argv) || owner.argv.some((arg:any)=>typeof arg!=='string')
    || !path.isAbsolute(owner.cwd) || !path.isAbsolute(owner.sessionPath) || !path.isAbsolute(owner.agentDir)
    || !owner.sessionPath.startsWith(`${owner.agentDir}${path.sep}sessions${path.sep}`)
    || typeof owner.arguments!=='string' || !owner.arguments.trim() || owner.arguments!==owner.arguments.trim()
    || /[\r\n]/.test(owner.arguments) || owner.argv.at(-1)!==`/memory ${owner.arguments}`
    || owner.argv.filter((arg:string)=>arg==='--session').length!==1
    || owner.argv[owner.argv.indexOf('--session')+1]!==owner.sessionPath
    || owner.argv.filter((arg:string)=>arg==='--model').length!==1
    || owner.argv[owner.argv.indexOf('--model')+1]!==owner.model
    || !owner.argv.includes('--print') || !owner.argv.includes('--mode')
    || owner.argv[owner.argv.indexOf('--mode')+1]!=='json')throw Error('Unbound native invocation');
  const original=nativeRows(input.originalSession),current=nativeRows(input.nativeSession);
  if(hash(input.originalSession)!==owner.priorSessionDigest || hash(input.nativeSession)!==completion.sessionDigest
    || hash(input.stdout)!==completion.stdoutDigest || !input.nativeSession.startsWith(input.originalSession)
    || original[0].cwd!==owner.cwd || current[0].id!==original[0].id
    || !exact(original,current.slice(0,original.length)))throw Error('Changed native prefix');
  if(!record(receipt) || receipt.kind!=='learning-pipeline-receipt' || receipt.version!==1
    || receipt.mode!=='manual' || receipt.operations<1 || !Array.isArray(receipt.attempts)
    || receipt.attempts.some((attempt:any)=>attempt.pendingOperations>0)
    || receipt.attempts.filter((attempt:any)=>attempt.phase==='memory').at(-1)?.outcome!=='applied')throw Error('Unapproved command receipt');
  const delivered=current.slice(original.length).filter(row=>row.type==='custom_message'
    && row.customType==='continual-learning-result');
  const stdout=input.stdout.trim().split('\n').map((line:string)=>JSON.parse(line));
  const emitted=stdout.filter((row:any)=>row.type==='message_end' && row.message?.customType==='continual-learning-result');
  if(delivered.length!==1 || !exact(delivered[0].details,receipt)
    || emitted.length!==1 || !exact(emitted[0].message.details,receipt))throw Error('Missing unique native receipt');
  const task=requestedMemoryTaskSlice(owner.arguments,original.slice(1));
  if(task.omittedEntries || task.omittedEvidenceEntries || !task.memoryRequest
    || task.memoryRequest.entryIndex!==task.entries.length-1)throw Error('Incomplete command projection');
  const snapshot=JSON.parse(input.snapshotText);
  const applied=receipt.attempts.filter((attempt:any)=>attempt.phase==='memory'
    && [0,1].includes(attempt.attempt) && attempt.outcome==='applied' && attempt.operations>0
    && attempt.usageLedgerId===usageLedger?.ledgerId && sameUsage(usageLedger?.knownUsage,attempt.usage));
  const initialLedger=input.initialUsageLedger;
  if(applied.length===1 && applied[0].attempt===0 && initialLedger!==undefined && !exact(initialLedger,usageLedger))
   throw Error('Changed original generation ledger');
  if(applied.length!==1 || applied[0].attempt===1 && (!record(initialLedger)
      || input.appliedUsageLedgerFile!==`memory-repair-usage-${usageLedger?.ledgerId}.json`
      || initialLedger.ledgerId===usageLedger?.ledgerId
      || initialLedger.ledgerId===sourceAudit?.usageLedger?.ledgerId
      || typeof initialLedger.complete!=='boolean'
      || receipt.attempts.filter((attempt:any)=>attempt.phase==='memory' && attempt.attempt===0
        && attempt.usageLedgerId===initialLedger.ledgerId && sameUsage(initialLedger.knownUsage,attempt.usage)).length!==1))
   throw Error('Missing original or applied generation ledger');
  if(!record(manifest) || manifest.cwd!==owner.cwd || manifest.snapshotPath!==path.join(manifest.runDir,'snapshot.json')
    || manifest.runDir!==path.join(owner.agentDir,'memory','runs',plan.scopeKey,plan.runId)
    || hash(input.snapshotText)!==manifest.snapshotDigest || snapshot.runId!==plan.runId
    || snapshot.scopeKey!==plan.scopeKey || plan.kind!=='memory-consolidation-plan' || plan.version!==1
    || !record(usageLedger) || typeof usageLedger.ledgerId!=='string' || typeof usageLedger.complete!=='boolean'
    || !record(sourceAudit) || !record(sourceAudit.usageLedger) || !record(sourceAudit.receipt)
    || typeof sourceAudit.usageLedger.complete!=='boolean'
    || sourceAudit.usageLedger.ledgerId!==sourceAudit.receipt.usageLedgerId
    || sourceAudit.usageLedger.ledgerId===usageLedger.ledgerId
    || !sameUsage(sourceAudit.usageLedger.knownUsage,sourceAudit.receipt.usage)
    || receipt.attempts.filter((attempt:any)=>attempt.phase==='memory' && attempt.attempt===0
      && attempt.operations===0 && attempt.usageLedgerId===sourceAudit.usageLedger.ledgerId
      && sameUsage(sourceAudit.usageLedger.knownUsage,attempt.usage)).length!==1)throw Error('Unbound source run or usage');
  if(!record(input.sources) || !record(owner.sourceHashes) || !exact(owner.sourceHashes,completion.sourceHashes)
    || !exact(Object.keys(input.sources).sort(),Object.keys(owner.sourceHashes).sort())
    || !Object.entries(input.sources).every(([relative,body])=>typeof body==='string'
      && owner.sourceHashes[relative]===hash(body)))throw Error('Changed current source inventory');
  if(owner.sourceFiles!==undefined && (!record(owner.sourceFiles) || !isDeepStrictEqual(owner.sourceFiles,completion.sourceFiles)
    || !isDeepStrictEqual(Object.keys(owner.sourceFiles).sort(),Object.keys(input.sources).sort())
    || Object.entries(input.sources).some(([name,body])=>{
     if(typeof body!=='string')return true;
     const value=owner.sourceFiles[name];
     return !record(value) || value.sha256!==hash(body) || !Number.isSafeInteger(value.mode) || value.mode<0 || value.mode>0o777
      || !Number.isSafeInteger(value.size) || value.size!==Buffer.byteLength(body);
    })))throw Error('Changed complete command source files');
  if(!Array.isArray(sourceAudit.observations) || !sourceAudit.observations.every((read:any)=>{
   if(typeof read?.path!=='string')return false;
   const relative=path.relative(owner.cwd,read.path);
   if(!relative || path.isAbsolute(relative) || relative.split(/[\\/]/).some(part=>!part || part==='.' || part==='..'
     || ['.memory','.pi','.git','node_modules','agents.md'].includes(part.toLowerCase())))return false;
   const body=input.sources[relative];
   if(read.error==='Scoped source path missing')return !Object.hasOwn(input.sources,relative);
   return typeof body==='string' && read.sha256===hash(body) && Number.isSafeInteger(read.offset) && read.offset>=1
    && Number.isSafeInteger(read.limit) && read.limit>=1 && read.limit<=2000
    && read.result===formatPlannerFileRead(body,read.offset,read.limit);
  }) || !reviewedSourceExtension(snapshot,plan,task.entries,manifest,sourceAudit,receipt as any))throw Error('Invalid current source extension');
  return {...base,ready:true,originalEntryCount:original.length,taskSlice:task,
    receiptDigest:hash(JSON.stringify(receipt)),snapshotDigest:hash(input.snapshotText)};
 }catch(error){return {...base,ready:false,reason:error instanceof Error?error.message:'Invalid command source proof'};}
}

/** Bind the actual CREATE-only initial plan to the complete stored corpus and
 * receipt-owned physical history. Independent semantics and original task
 * safety are still required; this never authorizes mutation. */
export function commandMemoryCorpusProof(input:any,prior:any,current:any):Record<string,unknown> {
 const base={mutationAuthority:false,initializationApproved:false,learningBenefitEstablished:false};
 try{
  if(!commandMemorySourceProof(input).ready || !record(prior) || !record(current)
    || !Array.isArray(prior.history) || !Array.isArray(current.history)
    || !record(prior.surfaceSnapshots) || !record(current.surfaceSnapshots)
    || !Array.isArray(current.memoryEntries) || !current.memoryEntries.length)throw Error('Missing command corpus inputs');
  const {plan,receipt}=input;
  if(!Array.isArray(plan.operations) || plan.operations.length || !Array.isArray(plan.newMemories)
    || plan.newMemories.length!==current.memoryEntries.length || receipt.operations!==plan.newMemories.length
    || receipt.attempts.filter((a:any)=>a.phase==='memory' && a.outcome==='applied')
      .reduce((sum:number,a:any)=>sum+a.operations,0)!==plan.newMemories.length)throw Error('Unbound initial plan operation count');
  const old=new Map(prior.history.map((row:any)=>[row.id,row]));
  if(old.size!==prior.history.length || new Set(current.history.map((row:any)=>row.id)).size!==current.history.length
    || prior.history.some((row:any)=>!current.history.some((next:any)=>exact(row,next))))throw Error('Changed prior history');
  const histories=current.history.filter((row:any)=>!old.has(row.id));
  if(!histories.length || histories.some((row:any)=>row.status!=='applied' || row.phase!=='memory'
    || row.batchId!==receipt.batchId || !Array.isArray(row.changes)))throw Error('Foreign or pending command history');
  const names=new Set<string>(),expectedPaths=new Set<string>();
  for(const proposal of plan.newMemories){
   const {name,content,classification}=proposal;
   if(typeof name!=='string' || path.basename(name)!==name || !name.endsWith('.md') || name==='MEMORY.md'
     || names.has(name.toLowerCase()) || typeof content!=='string' || !content.trim()
     || !['safe','private'].includes(classification))throw Error('Invalid complete initial plan');
   names.add(name.toLowerCase());
   const entries=current.memoryEntries.filter((entry:any)=>entry.filename===name);
   if(entries.length!==1 || entries[0].content!==content || entries[0].revision!==hash(content))throw Error('Corpus differs from approved plan');
   const roots=classification==='safe'?['private','public']:['private'];
   if(classification==='private' && Object.hasOwn(current.surfaceSnapshots,`project/.memory/${name}`))throw Error('Private entry has a public copy');
   for(const root of roots){
    const key=root==='public'?`project/.memory/${name}`:`private/${name}`;
    expectedPaths.add(key);
    const physical=current.surfaceSnapshots[key];
    const matches=histories.flatMap((row:any)=>row.changes).filter((change:any)=>change.target?.root===root && change.target.name===name);
    if(Object.hasOwn(prior.surfaceSnapshots,key) || !record(physical) || physical.digest!==hash(content)
      || physical.bytes!==Buffer.from(content).toString('base64')
      || typeof physical.revision!=='string' || !/^\d+:\d+:\d+:-?\d+:-?\d+$/.test(physical.revision)
      || Number(physical.revision.split(':')[2])!==Buffer.byteLength(content)
      || !Number.isSafeInteger(physical.mode) || physical.mode<0 || physical.mode>0o777
      || matches.length!==1 || matches[0].before!==null || !isDeepStrictEqual(matches[0].after,physical))throw Error('Missing complete mirrored physical history');
   }
  }
  for(const key of new Set([...Object.keys(prior.surfaceSnapshots),...Object.keys(current.surfaceSnapshots)])){
   if(expectedPaths.has(key) || ['private/MEMORY.md','project/.memory/MEMORY.md'].includes(key))continue;
   if(!exact(prior.surfaceSnapshots[key],current.surfaceSnapshots[key]))throw Error('Unexpected learned surface mutation');
   if((key.startsWith('private/') || key.startsWith('project/.memory/')) && key.endsWith('.md'))throw Error('Unlisted corpus entry');
  }
  if(histories.flatMap((row:any)=>row.changes).some((change:any)=>{
   const key=change.target?.root==='public'?`project/.memory/${change.target.name}`:`${change.target?.root}/${change.target?.name}`;
   return !expectedPaths.has(key) && !['private/MEMORY.md','project/.memory/MEMORY.md'].includes(key);
  }))throw Error('History contains a foreign operation');
  return {...base,ready:true,knowledgeOperations:plan.newMemories.length,
    reviewedMemoryCorpusDigest:hash(JSON.stringify(current.memoryEntries.map((entry:any)=>[entry.filename,entry.revision])))};
 }catch(error){return {...base,ready:false,reason:error instanceof Error?error.message:'Invalid command corpus'};}
}
