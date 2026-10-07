/** Research only: fixed arms, exact wires, controlled numeric observations. */
import {claimFrozenRequestHash} from './jev-deadline-research';
export const ORIGINAL_TRANSPORT_ARMS=['direct-5s','proxy-15s','proxy-5s','direct-15s'] as const;
export function originalTransportArm(id:string):{id:string;route:'direct'|'proxy';timeout:5000|15000} {
 if(!ORIGINAL_TRANSPORT_ARMS.some(v=>v===id))throw Error('Invalid original transport arm');
 return {id,route:id.startsWith('direct-')?'direct':'proxy',timeout:id.endsWith('-5s')?5000:15000};
}
export function originalTransportEndpoint(arm:{route:'direct'|'proxy'},proxy:string|undefined):string {
 if(arm.route==='direct')return 'https://api.typesafe.ai';
 const match=/^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})\/jev$/.exec(proxy??'');
 if(!match||Number(match[1])>65535)throw Error('Invalid owned proxy endpoint');
 return proxy!;
}
export function originalTransportWireGuard(hashes:readonly string[]):(digest:string)=>void {
 if(hashes.length!==3)throw Error('Incomplete original wire profile');
 const remaining=[...hashes];let count=0;
 return digest=>{if(count>=3)throw Error('Original transport request budget exceeded');claimFrozenRequestHash(remaining,digest);count++;};
}
export function verifyOriginalTransportWireSet(expected:readonly string[],actual:readonly string[]):void {
 if(expected.length!==3||actual.length!==3||JSON.stringify([...expected].sort())!==JSON.stringify([...actual].sort()))throw Error('Incomplete original transport collection');
}
/** Deliberately forced offline answers establish request coverage, never quality. */
export function originalTransportForcedResponse(request:{questions:Record<string,{type:string;criteria:Record<string,unknown>}>}):Response {
 const answers=Object.fromEntries(Object.entries(request.questions).map(([key,q])=>{
  if(q.type==='noul')return[key,{type:'noul',noul:.99}];
  const label=key.startsWith('expands_')?'same':key.startsWith('counter_')?'compatible':undefined;
  if(q.type!=='choice'||!label||!Object.hasOwn(q.criteria,label))throw Error('Unexpected original primitive');
  return[key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
 }));return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
}
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const probability=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1;
const tokens=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export interface OriginalTransportObservation {valid:boolean;modelVerified:boolean;inputTokens?:number;outputTokens?:number;judgments:{key:string;noul?:number;choice?:string;confidence?:number;probabilities?:Record<string,number>}[]}
export function originalTransportObservation(request:unknown,response:unknown):OriginalTransportObservation {
 const observation:OriginalTransportObservation={valid:false,modelVerified:record(response)&&response.model==='jev-1.13.0',judgments:[]};
 if(!record(request)||!record(request.questions)||!record(response)||!observation.modelVerified)return observation;
 if(record(response.usage)){if(tokens(response.usage.input_tokens))observation.inputTokens=response.usage.input_tokens;if(tokens(response.usage.output_tokens))observation.outputTokens=response.usage.output_tokens;}
 if(!record(response.answers)||Object.keys(response.answers).length!==Object.keys(request.questions).length)return observation;
 for(const [key,q]of Object.entries(request.questions)){
  const answer=response.answers[key];
  if(!/^(?:supported_\d+|expands_\d+|counter_\d+_\d+)$/.test(key)||!record(q)||!record(q.criteria)||!record(answer)||answer.type!==q.type)return observation;
  if(q.type==='noul'){
   if(!probability(answer.noul))return observation;observation.judgments.push({key,noul:answer.noul});
  }else if(q.type==='choice'){
   const labels=Object.keys(q.criteria),allowed=new Set(['same','narrower','broader','unclear','compatible','contradicts']);
   if(typeof answer.choice!=='string'||!labels.includes(answer.choice)||!probability(answer.confidence)||!record(answer.probabilities))return observation;
   const p=answer.probabilities;
   if(labels.length!==Object.keys(p).length||!labels.every(k=>allowed.has(k)&&probability(p[k]))||Math.abs(labels.reduce((n,k)=>n+Number(p[k]),0)-1)>=.02)return observation;
   observation.judgments.push({key,choice:answer.choice,confidence:answer.confidence,probabilities:Object.fromEntries(labels.map(k=>[k,Number(p[k])]))});
  }else return observation;
 }
 observation.valid=true;return observation;
}
export function originalTransportComplete(t:{model?:string;reason:string;requestCount?:number;completedRequests?:number;evidenceEntries?:number;coveredEntries?:number;evidenceWindows?:number;completedWindows?:number;inputTokens?:number},observations:readonly OriginalTransportObservation[]):boolean {
 return t.model==='jev-1.13.0'&&t.requestCount===3&&t.completedRequests===3&&t.evidenceEntries===17&&t.coveredEntries===17
  &&t.evidenceWindows===2&&t.completedWindows===2&&tokens(t.inputTokens)&&observations.length===3
  &&observations.every(o=>o.valid&&o.modelVerified&&tokens(o.inputTokens)&&tokens(o.outputTokens))
  &&!['timeout','unavailable','invalid-response','cancelled','bounds','sensitive'].includes(t.reason);
}
