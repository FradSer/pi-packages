import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, renameSync } from 'node:fs';
const profile=JSON.parse(readFileSync('/pilot/profile.json','utf8'));
const child=spawnSync(process.execPath,['/pilot/probe.mjs','/workspace/solution.mjs'],{encoding:'utf8',timeout:10000,maxBuffer:131072});
let observations;
try { observations=JSON.parse(child.stdout.trim()); }
catch { observations={outcomes:profile.names.map(name=>({name,passed:false})),passed:false,diagnostic:((child.stderr||'')+String(child.error||'')).slice(-6000)}; }
observations.task=readFileSync('/pilot/TASK.md','utf8');
const evidence={run:{suite:'frozen public behavior probes',observations},checks:profile.names.map((name,i)=>({clause:i+1,path:`outcomes.${i}.passed`,op:'equals',value:true}))};
const target=process.env.PI_E2E_EVIDENCE_PATH;
if(target){writeFileSync(target+'.tmp',JSON.stringify(evidence));renameSync(target+'.tmp',target)}
else console.log(JSON.stringify(evidence));
