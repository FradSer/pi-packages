/** Research-only syntax projection; parent identity is not user permission. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import type {createJevJudge, JevJudge} from '../extensions/jev-learning';
export interface BoundScopeContext {
 repoRoot:string; runId:string; scopeKey:string; evidenceDigest:string;
}
type OriginalValidate = JevJudge['validate'];
export type BoundScopeJudge = Omit<JevJudge,'validate'> & {
 validate(stage:Parameters<OriginalValidate>[0], evidence:unknown, candidates:readonly unknown[], existing:Parameters<OriginalValidate>[3], signal?:AbortSignal, harnessCitations?:unknown, parentScope?:BoundScopeContext):ReturnType<OriginalValidate>;
};
export type BoundScopeFactory = (...args:Parameters<typeof createJevJudge>)=>BoundScopeJudge;
export function boundScopeSource(source:string):string {
 const replace=(before:string,after:string)=>{if(source.split(before).length!==2)throw Error('Frozen bound-scope source changed');source=source.replace(before,after);};
 source='import {createHash} from "node:crypto";\nimport {projectPushTemplate} from "./harness-command-coverage";\n'+source;
 replace('export interface JevJudge {',String.raw`export interface BoundScopeContext {
  repoRoot: string; runId: string; scopeKey: string; evidenceDigest: string;
}
const boundMatching = "Code proves this parent-bound rule matches a subset of git push spellings within the current project: optional cd to the exact parent directory or dot followed by &&, and only -C . , -c core.quotePath=false or --no-pager global options. Further push arguments may follow. This is matching proof, never user permission.";
function boundPush(candidate: unknown, evidence: unknown, context?: BoundScopeContext): boolean {
  if (!context || !record(evidence) || context.runId !== evidence.runId || context.scopeKey !== evidence.scopeKey
    || !context.runId || !context.scopeKey || createHash("sha256").update(JSON.stringify(evidence)).digest("hex") !== context.evidenceDigest
    || !record(candidate) || candidate.op !== "addRule" || !record(candidate.rule)
    || candidate.rule.action !== "block" || candidate.rule.enabled === false) return false;
  const template = projectPushTemplate(context.repoRoot);
  return template !== undefined && candidate.rule.bash === template;
}
export interface JevJudge {`);
 replace('harnessCitations?: unknown): Promise<','harnessCitations?: unknown, parentScope?: BoundScopeContext): Promise<');
 replace('async validate(stage, evidence, candidates, existing, signal, harnessCitations) {','async validate(stage, evidence, candidates, existing, signal, harnessCitations, parentScope) {');
 replace('const familyCommand = stage === "harness" ? blockedCommandFamily(candidate) : undefined;','const boundFamily = stage === "harness" && boundPush(candidate, evidence, parentScope);\n        const familyCommand = stage === "harness" ? blockedCommandFamily(candidate) ?? (boundFamily ? "git push" : undefined) : undefined;');
 replace('matching: "The raw command starts with these unquoted words, separated by ASCII spaces or tabs. The final word has a word boundary. Additional arguments may follow. Vertical whitespace and Unicode whitespace cannot separate the command words."','matching: boundFamily ? boundMatching : "The raw command starts with these unquoted words, separated by ASCII spaces or tabs. The final word has a word boundary. Additional arguments may follow. Vertical whitespace and Unicode whitespace cannot separate the command words."');
 replace('candidate: counterevidenceMeaning(stage, candidate),','candidate: stage === "harness" && boundPush(candidate, evidence, parentScope) && record(candidate) && record(candidate.rule)\n                ? { rule: { commandWords: "git push", action: "block", message: candidate.rule.message as JsonValue, matching: boundMatching, scope: "current project" } }\n                : counterevidenceMeaning(stage, candidate),');
 return source;
}
export async function loadBoundScopeJudge(transform:(source:string)=>string = boundScopeSource):Promise<{createJevJudge:BoundScopeFactory;baselineCreateJevJudge:typeof createJevJudge;sourceSha256:string;patchedSha256:string;directory:string;dispose():Promise<void>}> {
 const source=await fs.readFile(new URL('./fixtures/jev-learning-before-bound-scope.ts.txt',import.meta.url),'utf8');const patched=transform(source);
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'jev-bound-scope-'));const dispose=()=>fs.rm(directory,{recursive:true,force:true});
 try {
  await fs.symlink(await fs.realpath(new URL('../node_modules/',import.meta.url)),path.join(directory,'node_modules'),'dir');
  await fs.cp(new URL('../extensions/',import.meta.url),`${directory}/extensions`,{recursive:true});
  const file=`${directory}/extensions/jev-learning.ts`;await fs.writeFile(file,patched,'utf8');
  const baselineFile=`${directory}/extensions/baseline-jev-learning.ts`;await fs.writeFile(baselineFile,source);
  const baseline:{createJevJudge:typeof createJevJudge}=await import(baselineFile);
  const loaded:{createJevJudge:BoundScopeFactory}=await import(file);const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
  return {createJevJudge:loaded.createJevJudge,baselineCreateJevJudge:baseline.createJevJudge,sourceSha256:hash(source),patchedSha256:hash(patched),directory,dispose};
 }catch(error){await dispose();throw error;}
}

/** V2 isolates semantic scope from syntax details already proven in code. */
export function boundScopeSourceV2(source:string):string {
 source=boundScopeSource(source);
 const before='Code proves this parent-bound rule matches a subset of git push spellings within the current project: optional cd to the exact parent directory or dot followed by &&, and only -C . , -c core.quotePath=false or --no-pager global options. Further push arguments may follow. This is matching proof, never user permission.';
 if(source.split(before).length!==2)throw Error('Frozen matching projection changed');
 source=source.replace(before,'Code proves this parent-bound rule matches only git push invocations in the current project. Further push arguments may follow. This is matching proof, never user permission.');
 const counter='Does this indexed window of the complete frozen evidence show that candidate.rule removes a user permission exception, expands a restriction, or lacks lasting authorization in the current project?';
 if(source.split(counter).length!==2)throw Error('Frozen counter question changed');
 const start=source.indexOf(counter)-1,end=source.indexOf('"',start+1)+1;
 const original=source.slice(start,end);
 const narrowed='Does any entry in this indexed window contradict, revoke or limit the proposed prohibition of candidate.rule.commandWords in candidate.rule.scope? Authorization and general argument scope are independently checked against supportEvidence; do not infer contradiction from missing repetition or irrelevant entries.'+original.slice(counter.length+1,-1);
 return source.slice(0,start)+'(boundPush(candidate, evidence, parentScope) ? '+JSON.stringify(narrowed)+' : '+original+')'+source.slice(end);
}
