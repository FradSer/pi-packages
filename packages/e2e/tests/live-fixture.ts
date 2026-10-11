import { appendFileSync, readFileSync } from "node:fs";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installScriptedProvider, type ScriptedTurn } from "../../../tests/e2e/support/scripted.ts";

export default function fixture(pi: ExtensionAPI): void {
  const source = "Feature: Test\nScenario: Works\nThen value is true\n";
  const runner = JSON.parse(readFileSync(path.join(process.cwd(), ".e2e", "runner.json"), "utf8"));
  delete runner.adapterFiles;
  const inline = {run: {observations: {value: true}}, checks: [{clause: 1, path: "value", op: "equals", value: true}]};
  const mode = process.env.PI_E2E_CASE ?? "fresh";
  if (mode === "provider-error") delete process.env.TYPESAFE_API_KEY;
  const turns: ScriptedTurn[] = mode === "requested-inline" ? [] : [{tool: "write", args: {path: "test.feature", content: source}}];
  if (mode === "retry") {
    turns.push({tool:"e2e_verify",args:{feature:"test.feature",runner,offline:true}});
    turns.push({tool:"write",args:{path:"adapter.mjs",content:`await import(${JSON.stringify(new URL("./run-fixture.mjs",import.meta.url).href)});`}});
    for(let attempt=0;attempt<3;attempt++) turns.push({tool:"e2e_verify",args:{feature:"test.feature",runner,offline:true}});
  }
  else if (mode === "inline" || mode === "requested-inline") turns.push({tool: "e2e_verify", args: {feature: "test.feature", evidence: inline, offline: true}});
  else if (mode === "failed") turns.push({tool: "e2e_verify", args: {feature: "test.feature", evidence: {...inline, run: {observations: {value: false}}}, offline: true}});
  else if (mode === "provider-error") turns.push({tool:"e2e_verify",args:{feature:"test.feature",evidence:{run:{observations:{value:true}}}}});
  else turns.push({tool: "e2e_verify", args: {feature: "test.feature", runner, offline: true}});
  installScriptedProvider(pi, {provider: "e2e-gate-scripted", probe: "e2e_gate_probe", turns});
  pi.on("agent_before_settle", (event, ctx) => {
    appendFileSync(path.join(ctx.cwd, "boundaries.jsonl"), JSON.stringify({continue: event.continue ?? false, entries: event.entries}) + "\n");
  });
}
