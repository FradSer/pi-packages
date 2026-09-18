/** Flat rule evaluator seam. Fixtures never execute commands. */
import { evaluateBash, evaluateSkill, evaluateText, mergeLayers } from "../extensions/guardrail-engine.ts";
import type { RuleLayer } from "../extensions/guardrail-types.ts";

const payload = JSON.parse(process.argv[2] ?? "{}") as {
  op: "merge" | "bash" | "skill" | "text";
  layers: RuleLayer[];
  availableSkills?: string[];
  command?: string;
  skill?: string;
  texts?: string[];
};
const config = mergeLayers(payload.layers, payload.availableSkills ? new Set(payload.availableSkills) : undefined);
const result = payload.op === "bash" ? evaluateBash(config, payload.command ?? "")
  : payload.op === "skill" ? evaluateSkill(config, payload.skill ?? "")
  : payload.op === "text" ? evaluateText(config, payload.texts ?? []) : config;
console.log(JSON.stringify(result));
