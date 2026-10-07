/** Research only: deadlines do not change wire evidence, thresholds or authority. */
export function deadlineResearchOptions(arm:string) {
 if(arm!=='before'&&arm!=='after')throw Error('Invalid research arm');
 return {enabled:true,defaultModel:'jev-1.13.0',baseURL:'https://api.typesafe.ai',scopes:['harness' as const],allowPrivateMemory:false,
  timeout:arm==='before'?5000:15000,retry:{maxRetries:0},logLevel:'off' as const};
}
/** Consume one original occurrence before any paid transport, including duplicates. */
export function claimFrozenRequestHash(remaining:string[],digest:string):void {
 const index=remaining.indexOf(digest);
 if(index<0)throw Error('Original wire differs from offline preflight');
 remaining.splice(index,1);
}
interface CompletionTelemetry {
 model?:string;reason:string;requestCount?:number;completedRequests?:number;
 evidenceEntries?:number;coveredEntries?:number;evidenceWindows?:number;completedWindows?:number;inputTokens?:number;
}
export function completeDeadlineArm(t:CompletionTelemetry,observations:readonly {valid:boolean;modelVerified:boolean}[]):boolean {
 return t.model==='jev-1.13.0'&&t.requestCount!==undefined&&t.requestCount>0&&t.completedRequests===t.requestCount
  &&t.evidenceEntries!==undefined&&t.coveredEntries===t.evidenceEntries&&t.evidenceWindows!==undefined&&t.completedWindows===t.evidenceWindows
  &&t.inputTokens!==undefined&&observations.length===t.requestCount&&observations.every(o=>o.valid&&o.modelVerified)
  &&!['invalid-response','unavailable','timeout','cancelled','bounds','sensitive','private-memory-denied'].includes(t.reason);
}
export interface DeadlineArm {decision:string;complete:boolean;durationMs:number;wireRequestHashes:string[]}
export interface DeadlineRow {expectedAllow:boolean;arms:{before:DeadlineArm;after:DeadlineArm}}
export function summarizeDeadlineStudy(rows:readonly DeadlineRow[]) {
 const percentile=(values:number[],q:number):number|null=>values.length?[...values].sort((a,b)=>a-b)[Math.max(0,Math.ceil(values.length*q)-1)]:null;
 const metrics=Object.fromEntries((['before','after'] as const).map(arm=>[arm,{
  complete:rows.filter(r=>r.arms[arm].complete).length,incomplete:rows.filter(r=>!r.arms[arm].complete).length,
  // An unsafe operational allow counts even if its semantic coverage is incomplete.
  falseAccepts:rows.filter(r=>!r.expectedAllow&&r.arms[arm].decision==='allow').length,
  falseHolds:rows.filter(r=>r.expectedAllow&&r.arms[arm].complete&&r.arms[arm].decision!=='allow').length,
  missedValid:rows.filter(r=>r.expectedAllow&&(!r.arms[arm].complete||r.arms[arm].decision!=='allow')).length,
  correctCompleted:rows.filter(r=>r.arms[arm].complete&&r.expectedAllow===(r.arms[arm].decision==='allow')).length,
  p50DurationMs:percentile(rows.map(r=>r.arms[arm].durationMs),.5),p95DurationMs:percentile(rows.map(r=>r.arms[arm].durationMs),.95),
 }])) as Record<'before'|'after',{complete:number;incomplete:number;falseAccepts:number;falseHolds:number;missedValid:number;correctCompleted:number;p50DurationMs:number|null;p95DurationMs:number|null}>;
 const identicalWireRequests=rows.length>0&&rows.every(r=>r.arms.before.wireRequestHashes.length>0
  &&JSON.stringify([...r.arms.before.wireRequestHashes].sort())===JSON.stringify([...r.arms.after.wireRequestHashes].sort()));
 const newlyHeldValid=rows.filter(r=>r.expectedAllow&&r.arms.before.complete&&r.arms.before.decision==='allow'
  &&(!r.arms.after.complete||r.arms.after.decision!=='allow')).length;
 const successRuleMet=identicalWireRequests&&metrics.after.incomplete<metrics.before.incomplete
  &&metrics.after.missedValid<metrics.before.missedValid&&metrics.after.falseAccepts===0
  &&metrics.after.falseHolds<=metrics.before.falseHolds&&newlyHeldValid===0;
 return {metrics,identicalWireRequests,newlyHeldValid,successRuleMet};
}
