import { createShadowSourceDirectory } from "./shadow-source-directory";
/** Research-only owned copy; knowledge projection retains every existing gate. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import type {createJevJudge} from '../extensions/jev-learning';
export function descriptionClaimSource(source:string):string {
 const before=String.raw`content: candidate.content.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, "")`;
 const after=String.raw`content: candidate.content.replace(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/, (_header: string, fields: string) => {
        const description = /(?:^|\r?\n)description:[ \t]*([^\r\n]*)/.exec(fields);
        return description?.[1].trim() ? "Memory index description (a proposed knowledge claim): " + description[1].trim() + "\n\n" : "";
      })`;
 if(source.split(before).length!==2)throw new Error('Frozen Memory projection changed');
 return source.replace(before,after);
}
export async function loadDescriptionClaimJudge():Promise<{createJevJudge:typeof createJevJudge;baselineCreateJevJudge:typeof createJevJudge;sourceSha256:string;patchedSha256:string;dispose():Promise<void>}> {
 const source=await fs.readFile(new URL('./fixtures/jev-learning-before-description.ts.txt',import.meta.url),'utf8');const patched=descriptionClaimSource(source);
 const directory=await createShadowSourceDirectory("jev-description-claim-");const dispose=()=>fs.rm(directory,{recursive:true,force:true});
 try {
  await fs.cp(new URL('../extensions/',import.meta.url),`${directory}/extensions`,{recursive:true});
  const file=`${directory}/extensions/jev-learning.ts`;await fs.writeFile(file,patched,'utf8');
  const baselineFile=`${directory}/extensions/baseline-jev-learning.ts`;await fs.writeFile(baselineFile,source);
  const baseline:{createJevJudge:typeof createJevJudge}=await import(baselineFile);
  const loaded:{createJevJudge:typeof createJevJudge}=await import(file);const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
  return {createJevJudge:loaded.createJevJudge,baselineCreateJevJudge:baseline.createJevJudge,sourceSha256:hash(source),patchedSha256:hash(patched),dispose};
 }catch(error){await dispose();throw error;}
}
