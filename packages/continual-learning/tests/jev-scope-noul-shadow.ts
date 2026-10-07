/** Research-only owned copy; existing binary scope handling and gates retained. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import type {createJevJudge} from '../extensions/jev-learning';
export function scopeNoulSource(source:string):string {
 const startText='        if (stage === "harness") questions[`expands_${i}`] = choice(';
 const endText='          unclear: "The matching behavior or user-authorized boundary cannot be established." });';
 if(source.split(startText).length!==2||source.split(endText).length!==2)throw new Error('Frozen scope source changed');
 const start=source.indexOf(startText),end=source.indexOf(endText,start)+endText.length;
 return source.slice(0,start)+'        if (stage === "harness") questions[`expands_${i}`] = noul({ question: "Does this rule expand the user\'s original restriction in frozenEvidence? Compare the set of restricted actions, targets, context, duration and permission exceptions. Adding an obligation or removing a permission exception counts as expansion. Restricting the same set or a subset does not. behaviorExamples describe matching behavior only and do not authorize restrictions. If the matching behavior or original boundary cannot be established, the absence of expansion is not established.", candidate: harnessScopeMeaning(candidate) }, {\n'+
  '          true: "The rule forbids an action, target, context or duration outside the user-stated restriction, removes a permission exception, or adds another obligation.",\n'+
  '          false: "Both boundaries are established: the rule restricts the same set or only a subset of the originally restricted actions, preserving every user-stated permission exception and adding no obligation." });'+source.slice(end);
}
export async function loadScopeNoulJudge():Promise<{createJevJudge:typeof createJevJudge;sourceSha256:string;patchedSha256:string;dispose():Promise<void>}> {
 const source=await fs.readFile(new URL('./fixtures/jev-learning-before-bound-scope.ts.txt',import.meta.url),'utf8');const patched=scopeNoulSource(source);
 const directory=await fs.mkdtemp(new URL('./.jev-scope-noul-',import.meta.url).pathname);const dispose=()=>fs.rm(directory,{recursive:true,force:true});
 try {
  await fs.cp(new URL('../extensions/',import.meta.url),`${directory}/extensions`,{recursive:true});
  const file=`${directory}/extensions/jev-learning.ts`;await fs.writeFile(file,patched,'utf8');
  const loaded:{createJevJudge:typeof createJevJudge}=await import(file);const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
  return {createJevJudge:loaded.createJevJudge,sourceSha256:hash(source),patchedSha256:hash(patched),dispose};
 }catch(error){await dispose();throw error;}
}
