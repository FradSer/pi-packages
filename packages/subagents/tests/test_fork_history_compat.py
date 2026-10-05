"""Persisted old messages do not turn parent tool activation into child authority."""
from __future__ import annotations

import json

from pathlib import Path

from subagents_helpers import SRC, run_node


def test_fork_filters_legacy_metadata_and_current_results_without_mutating_parent(tmp_path: Path) -> None:
    script = f"""
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ snapshotWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const usage={{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}}};
      const outputs=[];
      for (const legacy of [false,true]) {{
        const parent=SessionManager.inMemory(process.cwd());
        parent.appendMessage({{role:"user",content:"Read it",timestamp:1}});
        parent.appendMessage({{role:"assistant",content:[{{type:"toolCall",id:"read-1",name:"read",arguments:{{path:"file.ts"}}}}],
          api:"openai-completions",provider:"fixture",model:"fixture",stopReason:"toolUse",timestamp:2,usage}});
        parent.appendMessage({{role:"toolResult",toolCallId:"read-1",toolName:"read",
          content:[{{type:"text",text:"Original result"}}],isError:false,timestamp:3,
          details:{{parentOnly:true}},...(legacy?{{addedToolNames:["agent"]}}:{{}})}});
        const before=JSON.stringify(parent.getEntries());
        const snapshot=snapshotWorkContext(parent);
        const result=snapshot.find(m=>m.role==="toolResult");
        outputs.push({{text:result.content[0].text,details:"details" in result,
          activation:"addedToolNames" in result,unchanged:before===JSON.stringify(parent.getEntries())}});
      }}
      console.log(JSON.stringify(outputs));
    """
    assert run_node(script, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"}) == [
        {"text":"Original result", "details":False, "activation":False, "unchanged":True},
        {"text":"Original result", "details":False, "activation":False, "unchanged":True},
    ]


def test_fork_excludes_system_credentials_and_runtime_authority_preserving_native_history(tmp_path: Path) -> None:
    # The execution contract allows conversation evidence, never the parent's
    # prompt/tool checkpoint, credentials or a deferred provider operation.
    result = run_node(f"""
      import assert from "node:assert/strict";
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ snapshotWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const usage={{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}}};
      const assistant=(content,stopReason="stop")=>({{role:"assistant",content,api:"openai-completions",
        provider:"fixture",model:"fixture",timestamp:2,usage,stopReason}});
      const tool=(id,name="read")=>({{role:"toolResult",toolCallId:id,toolName:name,
        content:[{{type:"text",text:"Completed evidence"}}],isError:false,timestamp:3,
        details:{{credentials:"runtime-secret"}},addedToolNames:["agent"],
        nestedCalls:{{calls:[{{arguments:{{token:"runtime-secret"}}}}]}},runtimeAuthority:"parent-only"}});
      const parent=SessionManager.inMemory(process.cwd());
      parent.appendMessage({{role:"system",content:"parent-secret",timestamp:1,
        sections:{{credentials:"parent-secret"}},toolsAdded:[{{name:"parent_admin"}}]}});
      const origin=parent.appendMessage({{role:"user",content:[{{type:"text",text:"Request"}},
        {{type:"image",data:"aW1hZ2U=",mimeType:"image/png"}}],timestamp:1}});
      parent.appendMessage(assistant([{{type:"text",text:"Abandoned branch"}}]));
      parent.branchWithSummary(origin,"Native branch summary",{{credentials:"runtime-secret"}});
      const kept=parent.getLeafId();
      parent.appendMessage(assistant([
        {{type:"thinking",thinking:"Historical reasoning",thinkingSignature:"opaque-signature"}},
        {{type:"text",text:"Historical answer",textSignature:"text-signature"}},
        {{type:"toolCall",id:"done",name:"read",arguments:{{path:"file.ts"}}}},
        {{type:"toolCall",id:"pending",name:"read",arguments:{{path:"pending.ts"}}}}
      ],"toolUse"));
      parent.appendCustomMessageEntry("evidence","Custom evidence",true,{{credentials:"runtime-secret"}});
      parent.appendMessage(tool("done"));
      parent.appendMessage(tool("pending","wrong-name"));
      parent.appendCompaction("Native compaction summary",kept,100,{{credentials:"runtime-secret"}});
      parent.appendCustomEntry("authority",{{credentials:"runtime-secret",tools:["parent_admin"]}});
      parent.appendMessage(assistant([{{type:"text",text:"Deferred answer evidence"}}],"deferred"));
      parent.getLeafEntry().message.deferred={{provider:"fixture",api:"fixture",modelId:"fixture",
        id:"parent-operation",data:{{credentials:"runtime-secret"}}}};
      const before=JSON.stringify(parent.getEntries()),leaf=parent.getLeafId();
      const snapshot=snapshotWorkContext(parent),serialized=JSON.stringify(snapshot);
      assert.equal(before,JSON.stringify(parent.getEntries()));assert.equal(leaf,parent.getLeafId());
      assert.ok(!serialized.includes("parent-secret"));assert.ok(!serialized.includes("runtime-secret"));
      assert.ok(!serialized.includes("parent_admin"));assert.ok(!serialized.includes("parent-only"));
      assert.ok(!serialized.includes("pending"));assert.ok(!serialized.includes("Abandoned branch"));
      assert.equal(snapshot.filter(m=>m.role==="toolResult").length,1);
      assert.ok(snapshot.some(m=>m.role==="branchSummary"&&m.summary==="Native branch summary"));
      assert.ok(snapshot.some(m=>m.role==="compactionSummary"&&m.tokensBefore===100));
      assert.ok(serialized.includes("opaque-signature"));assert.ok(serialized.includes("text-signature"));
      assert.ok(serialized.includes("Deferred answer evidence"));
      snapshot.find(m=>m.role==="assistant").content[0].thinking="child mutation";
      assert.equal(before,JSON.stringify(parent.getEntries()));
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"})
    assert result == {"ok": True}


def test_completed_exchanges_keep_only_matching_results_across_custom_history(tmp_path: Path) -> None:
    result = run_node(f"""
      import assert from "node:assert/strict";
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ snapshotWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const usage={{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}}};
      const parent=SessionManager.inMemory(process.cwd());
      const call=(id)=>({{role:"assistant",content:[{{type:"toolCall",id,name:"read",arguments:{{}}}}],
        api:"openai-completions",provider:"fixture",model:"fixture",stopReason:"toolUse",timestamp:2,usage}});
      const result=(toolCallId,toolName="read")=>({{role:"toolResult",toolCallId,toolName,
        content:[{{type:"text",text:toolCallId}}],isError:false,timestamp:3}});
      parent.appendMessage({{role:"user",content:"Request",timestamp:1}});
      parent.appendMessage(call("matched"));
      parent.appendCustomMessageEntry("evidence","Interleaved history",true);
      parent.appendMessage(result("matched"));parent.appendMessage(result("matched"));
      parent.appendMessage(call("unmatched"));parent.appendMessage(result("unmatched","wrong"));
      parent.appendMessage({{role:"user",content:"New boundary",timestamp:4}});
      parent.appendMessage(result("unmatched"));parent.appendMessage(call("unfinished"));
      const snapshot=snapshotWorkContext(parent);
      assert.deepEqual(snapshot.map(m=>m.role),["user","assistant","custom","toolResult","user"]);
      assert.equal(snapshot[1].content[0].id,"matched");
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"})
    assert result == {"ok": True}


def test_durable_writer_preserves_summary_roles_in_private_history(tmp_path: Path) -> None:
    result = run_node(f"""
      import assert from "node:assert/strict";
      import {{ readFileSync,statSync }} from "node:fs";
      import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
      import {{ writeWorkContext }} from {json.dumps((SRC / "work-context.ts").as_uri())};
      const history=[{{role:"compactionSummary",summary:"Compacted marker",tokensBefore:12,timestamp:1}},
        {{role:"branchSummary",summary:"Branch marker",fromId:"historic-entry",timestamp:2}},
        {{role:"user",content:"Historical input",timestamp:3}}];
      const file=writeWorkContext(process.cwd(),{json.dumps(str(tmp_path))},history);
      const child=SessionManager.open(file);
      assert.deepEqual(child.buildSessionContext().messages,history);
      assert.equal(child.getHeader().parentSession,undefined);
      assert.equal(statSync(file).mode&0o777,0o600);
      assert.ok(readFileSync(file,"utf8").includes("Compacted marker"));
      console.log(JSON.stringify({{ok:true}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "PI_OFFLINE": "1"})
    assert result == {"ok": True}
