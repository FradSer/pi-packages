import fs from "node:fs/promises";
import path from "node:path";
import register from "/opt/experiment/packages/continual-learning/index.ts";
import {resolveMemoryPaths} from "/opt/experiment/packages/continual-learning/extensions/inject-memory.ts";
import {listLearningHistory} from "/opt/experiment/packages/continual-learning/extensions/learning-history.ts";

// Native fixture verification, not real main-model or Jev inference.
const quote = process.env.CL_NATIVE_LANGUAGE === "zh"
  ? "请记住：这个项目使用 pnpm，许可证是 MIT。一次缓存超时在重试后恢复了。"
  : "Remember: this project uses pnpm. Its license is MIT. A cache timeout cleared on retry.";
export default function (pi) {
  const commands = new Map();
  const fixtureRequests: {questionIds: string[]; returnedModel: string | null; unavailable: boolean}[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (!String(url).includes("typesafe")) return originalFetch(url, options);
    const request = JSON.parse(String(options?.body));
    if (process.env.CL_NATIVE_REAL_JEV_PROXY_URL) {
      return originalFetch(process.env.CL_NATIVE_REAL_JEV_PROXY_URL, {...options,
        headers:{"Content-Type":"application/json","Authorization":`Bearer ${process.env.CL_NATIVE_PROXY_TOKEN}`}});
    }
    const questionIds = Object.keys(request.questions);
    fixtureRequests.push({questionIds,returnedModel:process.env.CL_NATIVE_ARM === "jev-unavailable" ? null : "jev-1.13.0",unavailable:process.env.CL_NATIVE_ARM === "jev-unavailable"});
    if (process.env.CL_NATIVE_ARM === "jev-unavailable") {
      return new Response(JSON.stringify({error:{message:"Fixed service unavailable"}}),{status:503});
    }
    const answers = Object.fromEntries(questionIds.map(id => {
      const composed = ["jev-composed", "jev-composed-original"].includes(process.env.CL_NATIVE_ARM ?? "");
      const touchesHeld = JSON.parse(request.state).originalCandidates?.some(candidate => candidate.name === "cache.md");
      const label = id === "ready" ? "selfContained" : id === "relation" ? composed && touchesHeld ? "unclear" : "independent" : id.startsWith("counter_") ? "compatible"
        : id === "supported_1" || id === "supported_description_1" ? "transient" : "grounded";
      const labels = id === "ready" ? ["selfContained","needsOther","unresolved"] : id === "relation" ? ["independent","duplicate","conflict","dependent","unclear"]
        : id.startsWith("counter_") ? ["compatible","contradicts","unclear"]
        : ["grounded","speculative","transient","unsupported","unclear"];
      return [id,{type:"choice",choice:label,confidence:1,probabilities:Object.fromEntries(labels.map(key=>[key,key===label?1:0]))}];
    }));
    return new Response(JSON.stringify({model:"jev-1.13.0",answers,usage:{input_tokens:10,output_tokens:3}}));
  };
  const wrapped = new Proxy(pi, {get(target,key) {
    if (key === "registerCommand") return (name, definition) => {commands.set(name,definition);return target.registerCommand(name,definition);};
    const value = Reflect.get(target,key);return typeof value === "function" ? value.bind(target) : value;
  }});
  register(wrapped);
  pi.on("session_start",async (_event,ctx) => {
    try {
      await commands.get("memory").handler(quote,ctx);
      const paths = resolveMemoryPaths(ctx.cwd);
      const receipt = JSON.parse(await fs.readFile(path.join(paths.runsDir,"learning-pipeline-receipt.json"),"utf8"));
      const files = async dir => {try{return (await fs.readdir(dir)).sort();}catch{return [];} };
      const history = await listLearningHistory(ctx.cwd);
      const boundRequests = [];
      for(const name of await fs.readdir(paths.runsDir)) if(name.startsWith("run_")) {
        try {
          const dir=path.join(paths.runsDir,name);
          const dossier=JSON.parse(await fs.readFile(path.join(dir,"incremental-learning-dossier.json"),"utf8"));
          boundRequests.push(dossier.memoryRequest?.entryIndex===0 && dossier.taskSlice?.entries[0]?.message?.content===quote);
        } catch { /* Not every parent run holds a dossier. */ }
      }
      const privateFiles = await files(paths.harnessDir),publicFiles = await files(paths.publicDir);
      const bodies = {};
      for(const name of ["tools.md","cache.md","license.md"]) if(privateFiles.includes(name)) {
        bodies[name]={private:await fs.readFile(path.join(paths.harnessDir,name),"utf8"),public:await fs.readFile(path.join(paths.publicDir,name),"utf8")};
      }
      await fs.writeFile("/evidence/pipeline-result.json",JSON.stringify({receipt,fixtureRequests,privateFiles,publicFiles,bodies,
        history,boundRequests,agents:await fs.readFile(path.join(ctx.cwd,"AGENTS.md"),"utf8"),harnessFiles:await files(path.join(ctx.cwd,".pi"))},null,2));
    } finally {globalThis.fetch=originalFetch;}
  });
}
