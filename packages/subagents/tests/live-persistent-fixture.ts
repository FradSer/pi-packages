/** Manual isolated live check. Disk definitions are user-authored fixture inputs. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { executeChildIntent } from "../src/child-execution.ts";
import { terminateAllAgents } from "../src/spawner.ts";
import { getAgent, observeAgentRoster } from "../src/roster.ts";
import type { SessionNotice, SessionResultNotice } from "../src/session-result.ts";

const root=process.env.PI_LIVE_ISOLATED_ROOT;
assert.ok(root&&path.resolve(getAgentDir()).startsWith(path.resolve(root)+path.sep),"An explicit isolated root is required");
const notices:SessionNotice[]=[];
const observers=new Set<()=>void>();
const options={cwd:process.cwd(),leaderModel:()=>process.env.PI_LIVE_MODEL,thinking:()=>"off",
  deliverSessionResult:(notice:SessionNotice)=>{notices.push(notice);for(const update of observers)update();}};
function result(name:string,count=1):Promise<SessionResultNotice>{
  return new Promise((resolve,reject)=>{
    const read=()=>{const answers=notices.filter((n):n is SessionResultNotice=>n.name===name&&n.kind==="result");
      if(answers.length>=count){clearTimeout(timer);observers.delete(read);resolve(answers.at(-1)!);}};
    const timer=setTimeout(()=>{observers.delete(read);reject(new Error("Live answer deadline exceeded"));},90000);
    observers.add(read);read();
  });
}
const unsub=observeAgentRoster(()=>{for(const update of observers)update();});
try{
  const temporary=await executeChildIntent({name:"live-temporary",prompt:"Reply exactly temporary-complete",tools:[]},options);
  assert.equal(temporary.details.ok,true);await result("live-temporary");
  assert.equal(getAgent("live-temporary")?.status,"idle");
  await executeChildIntent({operation:"input",delivery:"next",session:temporary.details.session,prompt:"Reply exactly second-complete"},options);
  await result("live-temporary",2);
  assert.equal(getAgent("live-temporary")?.status,"idle");
  const directory=path.join(getAgentDir(),"agents","live-saved");fs.mkdirSync(directory,{recursive:true});
  fs.writeFileSync(path.join(directory,"agent.md"),"---\nname: live-saved\ndescription: Manual isolated fixture\ntools: read\n---\nRetain the marker supplied by the caller.\n");
  const first=await executeChildIntent({name:"live-saved",prompt:"Remember marker cobalt-713. Reply Saved."},options);
  assert.equal(first.details.ok,true);await result("live-saved");
  assert.equal(getAgent("live-saved")?.status,"idle");
  await executeChildIntent({operation:"stop",session:first.details.session},options);
  const second=await executeChildIntent({name:"live-saved",prompt:"What marker did I give you? Reply with only that marker."},options);
  assert.equal(second.details.ok,true);const resumed=await result("live-saved",2);assert.ok(resumed.text.includes("cobalt-713"));
  console.log(JSON.stringify({ok:true,temporaryIdle:true,persistentResumed:true}));
}finally{unsub();const closed=await terminateAllAgents();assert.ok(closed.every(item=>item.confirmedClosed));}
