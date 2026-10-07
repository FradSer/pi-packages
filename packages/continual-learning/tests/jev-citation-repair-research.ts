/** Public synthetic research only; complete original citations, never select by gold label. */
import type {NewMemoryEvidence} from '../extensions/consolidation-run';
import {containsSensitiveMemoryMaterial,normalizeNewMemoryProposals} from '../extensions/consolidation-run';
export function completePublicResearchCitations(snapshot:unknown,candidates:unknown[]){
 const original=normalizeNewMemoryProposals({newMemories:candidates},snapshot);
 if(JSON.stringify(original)!==JSON.stringify(candidates)||original.some(c=>c.classification!=='safe'))throw Error('Research requires unchanged normalized public candidates');
 if(!snapshot||typeof snapshot!=='object'||!('entries' in snapshot)||!Array.isArray(snapshot.entries))throw Error('Invalid research snapshot');
 const additions=snapshot.entries.flatMap((entry:unknown,index:number):NewMemoryEvidence[]=>{
  if(!entry||typeof entry!=='object'||!('role' in entry)||!('content' in entry))throw Error('Research requires explicit source entries');
  if(entry.role!=='user'&&entry.role!=='toolResult')return [];
  if(typeof entry.content!=='string'||!entry.content.trim()||entry.content.length>2000||containsSensitiveMemoryMaterial(entry.content))throw Error('Incomplete or unsafe research citation');
  return [{index,quote:entry.content,role:entry.role}];
 });
 const repaired=original.map(candidate=>{
  const evidence=[...candidate.evidence];
  for(const citation of additions)if(!evidence.some(e=>e.index===citation.index&&e.role===citation.role&&e.quote===citation.quote))evidence.push(citation);
  if(evidence.length>8)throw Error('Research citation capacity exceeded');
  return {...candidate,evidence};
 });
 const checked=normalizeNewMemoryProposals({newMemories:repaired},snapshot);
 if(JSON.stringify(checked)!==JSON.stringify(repaired))throw Error('Research changed candidate classification');
 return checked;
}
