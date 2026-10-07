/** Research only. Quote visibility cannot authorize writes or replace full review. */
import {containsSensitiveMemoryMaterial, normalizeSnapshotEvidence} from '../extensions/consolidation-run';
const record=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
export function anchorHarnessScopeCitation(init:RequestInit|undefined,snapshot:unknown,citations:unknown):RequestInit {
  if(!init||typeof init.body!=='string'||!record(snapshot)||snapshot.contextEnabled!==true||!Array.isArray(snapshot.entries)
    ||!Array.isArray(citations)||!citations.length)throw Error('Invalid research citation input');
  if(containsSensitiveMemoryMaterial(JSON.stringify({snapshot,citations})))throw Error('Sensitive research citation input');
  const quotes=new Map<number,string[]>(),citedIndexes=new Set<number>();
  for(const item of citations){
    if(!record(item)||!Number.isSafeInteger(item.index)||Number(item.index)<0||item.source!=='user'
      ||typeof item.quote!=='string'||!item.quote.trim()||item.quote.length>2000||!Number.isSafeInteger(item.count)||Number(item.count)<1)throw Error('Invalid research user citation');
    const indexes=item.eventIndex===undefined?snapshot.entries.map((_,index)=>index):[item.eventIndex];
    let matches=0;
    for(const index of indexes){try{const normalized=normalizeSnapshotEvidence([{index,quote:item.quote,role:'user'}],snapshot);citedIndexes.add(normalized[0].index);matches++}catch{/* Nonmatching entries cannot establish source identity. */}}
    if(matches<Number(item.count))throw Error('Research quote is absent from original user evidence');
    const original=quotes.get(Number(item.index))??[];if(!original.includes(item.quote))original.push(item.quote);
    if(original.length>8)throw Error('Research citation count exceeds bound');quotes.set(Number(item.index),original);
  }
  const request:unknown=JSON.parse(init.body);
  if(!record(request)||!record(request.questions))throw Error('Invalid research request');
  const state:unknown=typeof request.state==='string'?JSON.parse(request.state):request.state;
  for(const [key,value] of Object.entries(request.questions)){
    const match=/^family_(\d+)$/.exec(key);if(!match)continue;
    if(!record(value)||!record(value.instructions)||!record(value.instructions.candidate)||value.type!=='choice')throw Error('Unexpected research family question');
    const restrictions=quotes.get(Number(match[1]));if(!restrictions?.length)throw Error('Missing research user restriction');
    if(!record(state)||!record(state.frozenEvidence))throw Error('Research support state is absent');
    const {entries,...metadata}=snapshot;
    const expectedSupport={...metadata,totalEntries:(entries as unknown[]).length,
      entries:(entries as unknown[]).map((entry,index)=>({index,entry})).filter(item=>citedIndexes.has(item.index))};
    // The production support view is an exact whole-entry subset; later entries
    // remain in the unchanged complete counter windows, verified by preflight.
    const transmitted=JSON.stringify(state.frozenEvidence);
    if(transmitted!==JSON.stringify(snapshot)&&transmitted!==JSON.stringify(expectedSupport))throw Error('Research support state differs from original source');
    if(Object.hasOwn(value.instructions.candidate,'originalUserRestrictions'))throw Error('Research anchor already exists');
    value.instructions.candidate.originalUserRestrictions=[...restrictions];
  }
  const body=JSON.stringify(request);
  if(Buffer.byteLength(body)>64000)throw Error('Research request exceeds unchanged wire bound');
  return {...init,body};
}

/** Forced offline responses verify complete transport only, never model quality. */
export async function preflightHarnessCitationAnchor(
  input:{snapshot:unknown;plan:{operations:unknown[];evidence?:unknown}},after:boolean,
):Promise<{requests:number;windows:number}> {
  const {createJevJudge}=await import('../extensions/jev-learning');
  let requests=0,familyQuestions=0;
  const judge=createJevJudge({enabled:true,apiKey:'fixture-only',defaultModel:'jev-1.13.0',scopes:['harness'],allowPrivateMemory:false,fetch:async(_url,init)=>{
    const sent=after?anchorHarnessScopeCitation(init,input.snapshot,input.plan.evidence):init;
    const body=String(sent?.body);if(Buffer.byteLength(body)>64000)throw Error('Unchanged research wire bound');
    const request=JSON.parse(body) as {questions:Record<string,{type:string;criteria:Record<string,unknown>}>};requests++;
    const answers=Object.fromEntries(Object.entries(request.questions).map(([key,q])=>{
      if(key.startsWith('family_'))familyQuestions++;
      if(q.type!=='choice')throw Error('Unexpected research primitive');
      const label=key.startsWith('authority_')?'lasting':key.startsWith('family_')?'authorized':key.startsWith('counter_')?'compatible':'faithful';
      if(!Object.hasOwn(q.criteria,label))throw Error('Unexpected research criteria');
      return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
    }));
    return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
  }});
  const result=await judge.validate('harness',input.snapshot,input.plan.operations,[],undefined,input.plan.evidence),t=result.telemetry;
  if(!familyQuestions||!requests||result.decision!=='allow'||t.evidenceWindows===undefined||t.evidenceEntries===undefined
    ||t.completedWindows!==t.evidenceWindows||t.coveredEntries!==t.evidenceEntries||t.completedRequests!==t.requestCount)throw Error('Incomplete Harness anchor preflight');
  return {requests,windows:t.evidenceWindows};
}

export function observeHarnessAnchorJudgments(request:unknown,response:unknown,model:string):{
  valid:boolean;modelVerified:boolean;judgments:{key:string;choice:string;confidence:number;probabilities:Record<string,number>}[];
} {
  const bad={valid:false,modelVerified:record(response)&&response.model===model,judgments:[]};
  if(!record(request)||!record(request.questions)||!record(response)||response.model!==model||!record(response.answers))return bad;
  const keys=Object.keys(request.questions);if(keys.length!==Object.keys(response.answers).length)return bad;
  const judgments:{key:string;choice:string;confidence:number;probabilities:Record<string,number>}[]=[];
  const probability=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1;
  const allowed=new Set(['lasting','conditional','temporary','elsewhere','absent','authorized','extra','unclear','faithful','invented','compatible','contradicts']);
  for(const key of keys){
    const question=request.questions[key],answer=response.answers[key];
    if(!/^(?:authority_\d+|family_\d+|explanation_\d+|counter_\d+_\d+)$/.test(key)||!record(question)||question.type!=='choice'||!record(question.criteria)
      ||!record(answer)||answer.type!=='choice'||typeof answer.choice!=='string'||!probability(answer.confidence)||!record(answer.probabilities))return bad;
    const criteria=Object.keys(question.criteria),values=answer.probabilities;
    if(criteria.length!==Object.keys(values).length||!criteria.includes(answer.choice)||!criteria.every(k=>allowed.has(k)&&probability(values[k]))
      ||Math.abs(criteria.reduce((n,k)=>n+Number(values[k]),0)-1)>=.02)return bad;
    judgments.push({key,choice:answer.choice,confidence:answer.confidence,probabilities:Object.fromEntries(criteria.map(k=>[k,Number(values[k])]))});
  }
  return {valid:true,modelVerified:true,judgments};
}
