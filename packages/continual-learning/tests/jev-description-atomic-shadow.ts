/** Research-only owned copy; knowledge projection retains every existing gate. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import type {createJevJudge} from '../extensions/jev-learning';
export function atomicDescriptionSource(source:string):string {
 const replace=(before:string,after:string)=>{if(source.split(before).length!==2)throw new Error('Frozen atomic-description source changed');source=source.replace(before,after);};
 replace('function candidateMeaning(stage:', String.raw`function memoryDescriptionClaim(candidate: unknown): string | undefined {
  if (!record(candidate) || typeof candidate.content !== "string") return undefined;
  const header = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(candidate.content);
  if (!header) return undefined;
  const description = /(?:^|\r?\n)description:[ \t]*([^\r\n]*)/.exec(header[1]);
  return description?.[1].trim() || undefined;
}
function addDescriptionJudgments(stage: "memory" | "harness", candidates: readonly unknown[], questions: Questions, prefix: "supported" | "relation" | "counter", suffix = ""): void {
  if (stage !== "memory") return;
  for (const [i, candidate] of candidates.entries()) {
    const description = memoryDescriptionClaim(candidate);
    const original = questions[prefix + "_" + i + suffix];
    if (!description || !original) continue;
    const question = JSON.parse(JSON.stringify(original)) as Questions[string];
    if (!record(question.instructions)) throw new Error("Invalid description judgment instructions");
    question.instructions = { ...question.instructions, candidate: { content: description } };
    questions[prefix + "_description_" + i + suffix] = question;
  }
}
function candidateMeaning(stage:`);
 replace('      let evaluated: Awaited<ReturnType<typeof evaluate>>;', '      addDescriptionJudgments(stage, candidates, questions, "supported");\n      addDescriptionJudgments(stage, candidates, questions, "relation");\n      let evaluated: Awaited<ReturnType<typeof evaluate>>;');
 replace('        // Preflight ALL requests and existing bodies', '        for (const [jobIndex, job] of jobs.entries()) if (jobIndex > 0) addDescriptionJudgments(stage, candidates, job.questions, "counter", `_${jobIndex - 1}`);\n        // Preflight ALL requests and existing bodies');
 replace('counter: "counterevidence" };', 'counter: "counterevidence", supported_description: "support", relation_description: "relationship", counter_description: "counterevidence" };');
 replace('          if (answer.probabilities.unrelated + answer.probabilities.supplement >= YES)', '          if (key.startsWith("relation_description_") && answer.probabilities.unrelated + answer.probabilities.supplement + answer.probabilities.duplicate >= YES) return undefined;\n          if (answer.probabilities.unrelated + answer.probabilities.supplement >= YES)');
 const pattern='(supported|authority|explanation|expands|family|relation|counter)_';
 if(source.split(pattern).length!==3)throw new Error('Frozen location guards changed');
 source=source.replaceAll(pattern,'(supported(?:_description)?|authority|explanation|expands|family|relation(?:_description)?|counter(?:_description)?)_');
 return source;
}
export async function loadAtomicDescriptionJudge():Promise<{createJevJudge:typeof createJevJudge;baselineCreateJevJudge:typeof createJevJudge;sourceSha256:string;patchedSha256:string;dispose():Promise<void>}> {
 const source=await fs.readFile(new URL('./fixtures/jev-learning-before-description.ts.txt',import.meta.url),'utf8');const patched=atomicDescriptionSource(source);
 const directory=await fs.mkdtemp(new URL('./.jev-description-atomic-',import.meta.url).pathname);const dispose=()=>fs.rm(directory,{recursive:true,force:true});
 try {
  await fs.cp(new URL('../extensions/',import.meta.url),`${directory}/extensions`,{recursive:true});
  const file=`${directory}/extensions/jev-learning.ts`;await fs.writeFile(file,patched,'utf8');
  const baselineFile=`${directory}/extensions/baseline-jev-learning.ts`;await fs.writeFile(baselineFile,source);
  const baseline:{createJevJudge:typeof createJevJudge}=await import(baselineFile);
  const loaded:{createJevJudge:typeof createJevJudge}=await import(file);const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
  return {createJevJudge:loaded.createJevJudge,baselineCreateJevJudge:baseline.createJevJudge,sourceSha256:hash(source),patchedSha256:hash(patched),dispose};
 }catch(error){await dispose();throw error;}
}
