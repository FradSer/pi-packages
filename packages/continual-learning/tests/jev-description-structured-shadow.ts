/** Research-only owned copy; knowledge projection retains every existing gate. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import type {createJevJudge} from '../extensions/jev-learning';
export function structuredDescriptionSource(source:string):string {
 const replace=(before:string,after:string)=>{if(source.split(before).length!==2)throw new Error('Frozen description source changed');source=source.replace(before,after);};
 replace('function candidateMeaning(stage:', String.raw`function memoryDescriptionClaim(candidate: unknown): string | undefined {
  if (!record(candidate) || typeof candidate.content !== "string") return undefined;
  const header = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(candidate.content);
  if (!header) return undefined;
  const description = /(?:^|\r?\n)description:[ \t]*([^\r\n]*)/.exec(header[1]);
  return description?.[1].trim() || undefined;
}
function candidateMeaning(stage:`);
 replace('observations: candidate.observations, content:', 'observations: candidate.observations, description: memoryDescriptionClaim(candidate), content:');
 const projection='{ content: meaning.content }';
 if(source.split(projection).length!==3)throw new Error('Frozen knowledge projections changed');
 source=source.replaceAll(projection,'{ content: meaning.content, ...(typeof meaning.description === "string" ? { description: meaning.description } : {}) }');
 replace('? "Which category describes the claims in candidate.content based on frozenEvidence?', '? (typeof meaning.description === "string" ? "Check every knowledge claim in candidate.description as well as candidate.content against frozenEvidence. description is a proposed retrieval summary, not additional evidence. " : "") + "Which category describes the claims in candidate.content based on frozenEvidence?');
 replace('? "Does this indexed window of the complete frozen evidence contradict, retract or limit any claim in candidate.content?', '? (memoryDescriptionClaim(candidate) ? "Compare every knowledge claim in candidate.description as well as candidate.content against reviewEvidence. description is a proposed retrieval summary, not additional evidence. " : "") + "Does this indexed window of the complete frozen evidence contradict, retract or limit any claim in candidate.content?');
 return source;
}
export async function loadStructuredDescriptionJudge():Promise<{createJevJudge:typeof createJevJudge;baselineCreateJevJudge:typeof createJevJudge;sourceSha256:string;patchedSha256:string;dispose():Promise<void>}> {
 const source=await fs.readFile(new URL('./fixtures/jev-learning-before-description.ts.txt',import.meta.url),'utf8');const patched=structuredDescriptionSource(source);
 const directory=await fs.mkdtemp(new URL('./.jev-description-structured-',import.meta.url).pathname);const dispose=()=>fs.rm(directory,{recursive:true,force:true});
 try {
  await fs.cp(new URL('../extensions/',import.meta.url),`${directory}/extensions`,{recursive:true});
  const file=`${directory}/extensions/jev-learning.ts`;await fs.writeFile(file,patched,'utf8');
  const baselineFile=`${directory}/extensions/baseline-jev-learning.ts`;await fs.writeFile(baselineFile,source);
  const baseline:{createJevJudge:typeof createJevJudge}=await import(baselineFile);
  const loaded:{createJevJudge:typeof createJevJudge}=await import(file);const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
  return {createJevJudge:loaded.createJevJudge,baselineCreateJevJudge:baseline.createJevJudge,sourceSha256:hash(source),patchedSha256:hash(patched),dispose};
 }catch(error){await dispose();throw error;}
}
