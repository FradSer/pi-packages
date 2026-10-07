"""Grade structured heldout findings and confirm native Memory tool evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re


def findings(text: str) -> list[dict] | None:
    for match in re.finditer(r"\{", text):
        try:
            value, _ = json.JSONDecoder().raw_decode(text[match.start():])
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("findings"), list):
            return value["findings"]
    return None


def score(root: Path) -> dict:
    study = json.loads((root / "study.json").read_text())
    audits = []
    for file in sorted(root.glob("child-*.jsonl")):
        events = [json.loads(line) for line in file.read_text().splitlines()]
        calls = {event["id"]: event for event in events if event.get("event") == "call"}
        reads = []
        memory_actions = []
        for event in events:
            if event.get("event") != "result":
                continue
            call = calls.get(event.get("id"), {})
            if event.get("tool") == "read" and "/memory/" in str(call.get("args", {}).get("path", "")):
                reads.append({"args":call.get("args"),"error":event.get("error"),"content":event.get("content")})
            if event.get("tool") == "agent_memory":
                memory_actions.append({"args":call.get("args"),"error":event.get("error"),"details":event.get("details")})
        audits.append({"file":file.name,"memoryIndexInjected":any(e.get("memory") for e in events if e.get("event")=="system"),"reads":reads,"memoryActions":memory_actions})
    spawns=json.loads((root / "spawns.json").read_text())
    capability=next((m["body"] for m in study.get("memoryFiles",[]) if m["file"]=="pi-review-boundaries.md"),"")
    evaluations = []
    for case in study.get("evaluations", []):
        notice = case["notice"]
        parsed = findings(notice.get("text", "")) if notice.get("kind") == "result" else None
        codes = [f.get("code") for f in parsed if isinstance(f, dict)] if parsed is not None else []
        expected = case["expected"]
        spawn=next((s for s in spawns if s["name"]==case["data"]["name"] and s.get("sessionDir")==case["data"].get("sessionDir")),{})
        audit=next((a for a in audits if a["file"]==f"child-{spawn.get('result',{}).get('pid')}.jsonl"),{})
        full_read=any(not r.get("error") and r.get("args",{}).get("path","").endswith("/pi-review-boundaries.md") and capability and capability.strip() in "\n".join(b.get("text","") for b in r.get("content",[]) if isinstance(b,dict)) for r in audit.get("reads",[]))
        evaluations.append({"case":case["case"],"auditFile":audit.get("file"),"memoryIndexInjected":audit.get("memoryIndexInjected",False),"fullEntryRead":full_read,"withMemory":case["withMemory"],"resultKind":notice["kind"],"parseable":parsed is not None,"missingCoverage":parsed is None,"codes":codes,
            "correct":parsed is not None and codes == ([expected] if expected else []),
            "falsePositives":sum(code != expected for code in codes),"missed":(expected is not None and expected not in codes) if parsed is not None else None})
    lifecycle = [{"saved":c["saved"],"attempt":c["attempt"],"first":c["first"]["kind"],"second":c["second"]["kind"],"idle":c.get("idle"),"stopOk":c["stop"]["ok"],"staleRefused":not c["stale"]["ok"]} for c in study.get("lifecycle", [])]
    return {"piVersion":study["piVersion"],"model":study["model"],"completed":study.get("completed",False),"error":study.get("error"),"lifecycle":lifecycle,"evaluations":evaluations,"audit":audits,
        "scores":{str(arm):{"correct":sum(e["correct"] for e in evaluations if e["withMemory"] == arm),"total":sum(e["withMemory"] == arm and not e["missingCoverage"] for e in evaluations),"attempted":sum(e["withMemory"] == arm for e in evaluations),"missingCoverage":sum(e["withMemory"] == arm and e["missingCoverage"] for e in evaluations),"falsePositives":sum(e["falsePositives"] for e in evaluations if e["withMemory"] == arm)} for arm in (False,True)}}


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("root",type=Path)
    args=parser.parse_args()
    result=score(args.root)
    (args.root/"summary.json").write_text(json.dumps(result,indent=2))
    print(json.dumps({key:value for key,value in result.items() if key != "audit"},indent=2))


if __name__=="__main__":main()
