/** Research-only chronology context; never a verdict or parent write authority. */
type RecordValue=Record<string,unknown>;
const record=(v:unknown):v is RecordValue=>!!v&&typeof v==='object'&&!Array.isArray(v);
const index=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export function temporalCounterRequest(body:string,candidates:readonly unknown[]):string {
 const request:unknown=JSON.parse(body);
 if(!record(request)||!record(request.questions))throw Error('Invalid research request');
 const keys=Object.keys(request.questions).filter(k=>/^counter(?:_description)?_\d+_\d+$/.test(k));
 if(!keys.length)return body;
 const state:unknown=typeof request.state==='string'?JSON.parse(request.state):request.state;
 if(!record(state)||!record(state.reviewEvidence)||!Array.isArray(state.reviewEvidence.entries))throw Error('Missing original review window');
 const windowIndexes=state.reviewEvidence.entries.map(entry=>{
  if(!record(entry)||!index(entry.index))throw Error('Invalid original window index');return entry.index;
 });
 if(!windowIndexes.length||windowIndexes.some((v,i)=>i>0&&v!==windowIndexes[i-1]+1))throw Error('Incomplete original review window');
 const questions={...request.questions};
 for(const key of keys){
  const candidateIndex=Number(/^counter(?:_description)?_(\d+)_\d+$/.exec(key)![1]);
  const candidate=candidates[candidateIndex],question=questions[key];
  if(!record(candidate)||!Array.isArray(candidate.evidence)||!record(question)||question.type!=='choice'||!record(question.instructions))throw Error('Missing original candidate or instructions');
  const citedIndexes=candidate.evidence.map(item=>{if(!record(item)||!index(item.index))throw Error('Invalid original citation');return item.index;});
  if(!citedIndexes.length)throw Error('Missing original citations');
  questions[key]={...question,instructions:{...question.instructions,
   chronology:{originalCitedEntryIndexes:citedIndexes,originalWindowEntryIndexes:windowIndexes},
   temporalRule:'Compare the original entry indexes and the actual claim scope. A failure before a cited verified success does not erase that later successful verification; a claim of guaranteed future success still requires evidence. A later user correction can replace an earlier fact or preference, but later mention alone does not establish verification or erase an unresolved contradiction. An assistant assertion is never verified observation. Later revocations and permission exceptions still limit the candidate. Decide the original counter question; chronology alone supplies neither support nor permission.'}};
 }
 return JSON.stringify({...request,questions});
}
