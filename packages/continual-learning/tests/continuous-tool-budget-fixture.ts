import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createAssistantMessageEventStream, getCurrentTools, type AssistantMessage } from "@earendil-works/pi-ai";
import { installStudyToolBudget } from "./continuous-tool-budget.ts";

export default function fixture(pi: ExtensionAPI): void {
  const environmentProbe = process.env.STUDY_BASH_ENVIRONMENT_PROBE === "1";
  if (environmentProbe) {
    pi.on("agent_settled", async () => {
      const {createJevJudge} = await import("../extensions/jev-learning.ts");
      const {containsSensitiveMemoryMaterial} = await import("../extensions/consolidation-run.ts");
      const observations = toolObservations;
      let authenticatedRequests = 0;
      let reviewRequests = 0;
      const judge = createJevJudge({enabled:true, defaultModel:"jev-1.14.0", fetch:async (_url, init) => {
        reviewRequests++;
        if (new Headers(init?.headers).get("Authorization") === `Bearer ${process.env.TYPESAFE_API_KEY}`) authenticatedRequests++;
        const request = JSON.parse(String(init?.body));
        const answers = Object.fromEntries(Object.entries(request.questions).map(([key, value]) => {
          const question = value as {criteria: Record<string, unknown>};
          const choice = key.startsWith("counter_") || key.startsWith("coherence_") ? "compatible" : "grounded";
          return [key,{type:"choice",choice,confidence:1,probabilities:Object.fromEntries(Object.keys(question.criteria).map(name => [name, name === choice ? 1 : 0]))}];
        }));
        return new Response(JSON.stringify({model:"jev-1.14.0",answers,usage:{input_tokens:0,output_tokens:0}}));
      }});
      const quote = "Remember this project uses pnpm.";
      const result = await judge.validate("memory", {contextEnabled:true,entries:[{role:"user",content:quote},...observations]},
        [{name:"project-pnpm.md",kind:"project",classification:"safe",content:"---\nname: project-pnpm\ndescription: Project package manager\ntype: project\n---\nUse pnpm for this project.",evidence:[{index:0,quote}]}], []);
      pi.appendEntry("study-bash-environment-proof", {parentCredentialAvailable:Boolean(process.env.TYPESAFE_API_KEY),
        observationSensitive:containsSensitiveMemoryMaterial(JSON.stringify(observations)), authenticatedRequests, reviewRequests,
        decision:result.decision, reason:result.telemetry.reason,telemetry:result.telemetry});
    });
  }
  const toolObservations: unknown[] = [];
  if (environmentProbe) {
    pi.on("tool_call", event => {toolObservations.push({role:"assistant",content:[{type:"toolCall",id:event.toolCallId,name:event.toolName,arguments:event.input}]});});
    pi.on("tool_result", event => {toolObservations.push({role:"toolResult",toolCallId:event.toolCallId,toolName:event.toolName,isError:event.isError,content:event.content});});
  }
  installStudyToolBudget(pi, 2);
  let calls = 0;
  pi.registerProvider("study-budget-fixture", {
    api: "study-budget-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "deterministic", name: "Study budget fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      calls++;
      pi.appendEntry("study-budget-provider", { call: calls, tools: getCurrentTools(context.messages).map(tool => tool.name) });
      if (environmentProbe && calls === 1) pi.appendEntry("study-bash-environment-wire", {tools:getCurrentTools(context.messages)});
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: environmentProbe && calls === 1 ? [{type:"toolCall",id:"environment",name:"bash",arguments:{command:"env | grep -i -E 'PI_|MEMORY|PLUGIN' | sort"}}] : calls === 1 || process.env.STUDY_BUDGET_REPEAT_TOOLS === "1" ? (calls === 1 ? ["one", "two", "forbidden"] : ["forbidden"]).map(name => ({
          type: "toolCall" as const, id: name, name: "bash", arguments: { command: `printf observed > ${name}` },
        })) : [{ type: "text", text: "Summarized existing observations." }],
        stopReason: calls === 1 || process.env.STUDY_BUDGET_REPEAT_TOOLS === "1" ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason, message });
      stream.end();
      return stream;
    },
  });
}
