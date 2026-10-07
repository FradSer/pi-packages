"""Isolated native Pi --print diagnostic probe; no real inference or writes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[3]
TESTS = Path(__file__).resolve().parent


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cl-counter-window-") as temp:
        root = Path(temp)
        agent = root / "agent"
        agent.mkdir()
        (agent / "settings.json").write_text('{"packages":[],"enableTelemetry":false}')
        extension = root / "probe.ts"
        imports = {
            "ai": str(REPO / "node_modules/@earendil-works/pi-ai/dist/index.js"),
            "judge": str(TESTS.parent / "extensions/jev-learning.ts"),
            "receipt": str(TESTS.parent / "extensions/learning-efficiency.ts"),
            "result": str(root / "result.json"),
        }
        extension.write_text('''
import fs from 'node:fs/promises';
import {createAssistantMessageEventStream} from AI_IMPORT;
import {createJevJudge,jevRepairFailureHints} from JUDGE_IMPORT;
import {buildLearningReceipt,learningSummaryDetails} from RECEIPT_IMPORT;
export default function(pi){
 let providerRequests=0;
 globalThis.fetch=async()=>{throw Error('Unexpected external request');};
 pi.registerProvider('counter-window-fixture',{
  baseUrl:'http://127.0.0.1.invalid',apiKey:'fixture',api:'openai-completions',
  models:[{id:'offline',name:'Offline diagnostic fixture',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:128000,maxTokens:100}],
  streamSimple(model){providerRequests++;const stream=createAssistantMessageEventStream();
   const message={role:'assistant',content:[{type:'text',text:'Counter-window fixture completed.'}],api:model.api,provider:model.provider,model:model.id,usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:Date.now()};
   queueMicrotask(()=>{stream.push({type:'done',reason:'stop',message});stream.end();});return stream;
  }
 });
 pi.on('before_agent_start',async()=>{
  const quote='This project uses pnpm.';
  const snapshot={contextEnabled:true,entries:[{role:'user',content:quote},{role:'toolResult',content:'Public observation. '.repeat(1300)},{role:'user',content:'Unrelated public note.'}]};
  const candidate={name:'fact.md',kind:'project',classification:'safe',content:`---\\nname: fact\\ndescription: ${quote}\\ntype: project\\n---\\n${quote}`,evidence:[{index:0,quote,role:'user'}]};
  const judge=createJevJudge({enabled:true,apiKey:'fixture',scopes:['memory'],fetch:async(_url,init)=>{
   const r=JSON.parse(String(init.body)),answers={};
   for(const[k,q]of Object.entries(r.questions)){const label=k==='counter_description_0_1'?'unclear':k.startsWith('supported')?'grounded':'compatible';answers[k]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===label?1:0]))};}
   return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:0}}));
  }});
  const verdict=await judge.validate('memory',snapshot,[candidate],[]);
  const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'proposed',durationMs:1,operations:0,jev:verdict.telemetry}]);
  await fs.writeFile(RESULT_PATH,JSON.stringify({verdict,receipt,lines:learningSummaryDetails(receipt),hints:jevRepairFailureHints(verdict.telemetry)}));
 });
 pi.on('session_shutdown',async()=>{const result=JSON.parse(await fs.readFile(RESULT_PATH,'utf8'));await fs.writeFile(RESULT_PATH,JSON.stringify({...result,providerRequests}));});
}
'''.replace("AI_IMPORT", json.dumps(imports["ai"]))
            .replace("JUDGE_IMPORT", json.dumps(imports["judge"]))
            .replace("RECEIPT_IMPORT", json.dumps(imports["receipt"]))
            .replace("RESULT_PATH", json.dumps(imports["result"])))
        env = {
            key: value for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL", "TMPDIR"}
        }
        env.update({"HOME": str(root), "PI_CODING_AGENT_DIR": str(agent),
                    "PI_OFFLINE": "1", "PI_TELEMETRY": "0"})
        cli = REPO / "node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
        command = ["node", str(cli), "--offline", "--print", "--no-session",
                   "--no-extensions", "--no-skills", "--no-prompt-templates",
                   "--no-themes", "--no-context-files", "--no-tools", "-e",
                   str(extension), "--provider", "counter-window-fixture", "--model",
                   "offline", "Check the public diagnostic fixture."]
        process = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                 text=True, timeout=60, check=False)
        if process.returncode != 0:
            raise RuntimeError(f"Native Pi diagnostic failed: {process.returncode}: {process.stderr[:2000]}")
        result = json.loads((root / "result.json").read_text())
        telemetry = result["verdict"]["telemetry"]
        assert result["verdict"]["decision"] == "propose"
        assert telemetry["field"] == "description"
        assert telemetry["evidenceWindowIndex"] == 1
        assert telemetry["evidenceEntryStart"] == telemetry["evidenceEntryEnd"] == 1
        assert telemetry["completedWindows"] == telemetry["evidenceWindows"] == 3
        assert "window 1 entries 1-1" in "\n".join(result["lines"])
        assert "window 1 entries 1-1" in "\n".join(result["hints"])
        assert result["receipt"]["operations"] == 0
        assert result["providerRequests"] == 1
        assert not list(root.rglob("fact.md"))
        version = subprocess.check_output(["node", str(cli), "--version"], env=env,
                                          cwd=root, text=True, timeout=30).strip()
        report = {"evidence": "native-pi-print-offline-counter-window-fixture",
                  "piVersion": version, "exitCode": process.returncode,
                  "externalRequests": 0, "fixtureProviderRequests": 1,
                  "decision": "propose", "field": "description",
                  "evidenceWindowIndex": 1, "evidenceEntryStart": 1,
                  "evidenceEntryEnd": 1, "completeEvidenceWindows": 3,
                  "productionCandidateWrites": 0,
                  "limitations": ["Mocked judgment integration, not real Jev quality.",
                                  "No TUI or new Docker workflow."]}
        output = TESTS / "jev-counter-window-native-print-evidence.json"
        with output.open("x") as destination:
            json.dump(report, destination, indent=2)
            destination.write("\n")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
