/** Research-only body context; never evidence, authority or permission. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import type {createJevJudge} from '../extensions/jev-learning';
export function descriptionContextSource(source:string):string {
 const before='    question.instructions = { ...question.instructions, candidate: { content: description } };';
 if(source.split(before).length!==2)throw Error('Frozen description projection changed');
 return source.replace(before,`    const meaning = candidateMeaning(stage, candidate);
    const bodyContext = record(meaning) && typeof meaning.content === "string" ? meaning.content : undefined;
    question.instructions = { ...question.instructions,
      question: String(question.instructions.question) + " candidate.content is the index description: it may be a retrieval cue naming when to read this Memory rather than a standalone factual assertion. Interpret its referents within bodyContext. bodyContext is proposed content, not evidence or authorization, and its grounding is checked independently. The description must not introduce facts, obligations or retrieval scope beyond the original evidence and proposed body. Judge only the description here; an unsupported claim remains unsupported even if asserted in bodyContext. Keep later corrections and permission exceptions.",
      candidate: { content: description, ...(bodyContext !== undefined ? { bodyContext } : {}) } };`);
}
export async function loadDescriptionContextJudge():Promise<{createJevJudge:typeof createJevJudge;sourceSha256:string;patchedSha256:string;directory:string;dispose():Promise<void>}> {
 const source=await fs.readFile(new URL('../extensions/jev-learning.ts',import.meta.url),'utf8');const patched=descriptionContextSource(source);
 const directory=await fs.mkdtemp(new URL('./.jev-description-context-',import.meta.url).pathname);const dispose=()=>fs.rm(directory,{recursive:true,force:true});
 try {
  await fs.cp(new URL('../extensions/',import.meta.url),`${directory}/extensions`,{recursive:true});
  const file=`${directory}/extensions/jev-learning.ts`;await fs.writeFile(file,patched,'utf8');
  const loaded:{createJevJudge:typeof createJevJudge}=await import(file);const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
  return {createJevJudge:loaded.createJevJudge,sourceSha256:hash(source),patchedSha256:hash(patched),directory,dispose};
 }catch(error){await dispose();throw error;}
}
