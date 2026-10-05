/** Real Jev re-evaluation of the archived public native formatting candidate.
 * This is semantic inference over real generated output, not a new Pi workflow.
 */
import fs from 'node:fs/promises';
import {createJevJudge} from '../extensions/jev-learning';
const report=JSON.parse(await fs.readFile(new URL('./jev-strict-current-native.json',import.meta.url),'utf8'));
const run=report.runs[0];
const proposal=run.history.find((h:{status:string;proposal?:unknown})=>h.status==='proposed').proposal;
const source=run.sourceMessages.find((m:{role:string})=>m.role==='user');
const existing=proposal.selected.map((name:string)=>({name,classification:'safe' as const,type:/^type:[ \t]*(.*)$/m.exec(run.privateMemory[name])?.[1]??'',description:/^description:[ \t]*(.*)$/m.exec(run.privateMemory[name])?.[1]??'',content:run.privateMemory[name]}));
const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0'});
const result=await judge.validate('memory',{entries:[{message:source}]},proposal.operations,existing);
console.log(JSON.stringify({evidence:'real-jev-inference-over-archived-native-candidate',sourceArtifact:'jev-strict-current-native.json',originalOutcome:'propose',originalReason:'duplicate',result},null,2));
if(result.decision!=='allow'||result.telemetry.model!=='jev-1.13.0')process.exitCode=1;
