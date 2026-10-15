/** Run-start prompt contract through the registered lifecycle boundary. */
import { observedAssert as assert, observeScenario, observedScenarios } from "../../../tests/e2e/support/assertion-observer.ts";
import { writeFileSync } from "node:fs";
import { registerGoalEvents } from "../src/events.ts";
import { normalizeGoalRecord } from "../src/record.ts";
import { GoalCore } from "../src/core.ts";
import { GOAL_PROCEDURE_ENTRY } from "../src/procedure.ts";
const results: string[] = [];
const handlers = new Map<string, Function>();
let accepted: unknown;
const activation = { pendingSetting: undefined as unknown, activationGoalId: undefined as unknown,
  owner: () => "fixture-owner", get goal() { return focused; },
  cancelGoalActivation: GoalCore.prototype.cancelGoalActivation };
let focused: ReturnType<typeof normalizeGoalRecord>;
const core = {
  pi: { on(name: string, handler: Function) { handlers.set(name, handler); } },
  get goal() { return focused; },
  acceptGoalSetting(prompt: string) {
    accepted = prompt;
    GoalCore.prototype.acceptGoalSetting.call(activation as unknown as GoalCore, prompt);
  },
  settings() { return {}; },
  currentUnmet() { return undefined; },
} as unknown as GoalCore;
registerGoalEvents(core);
try {
  await observeScenario("Capability notes require an explicit persistent Goal request", async () => {
    assert.equal(handlers.has("context"), false, "no per-request injection or replay");
    const options = { sections: { other: "Existing guideline" } };
    const event = { messageType: "user", prompt: "ordinary work", systemPrompt: "Original system", systemPromptOptions: options };
    const first = await handlers.get("before_agent_start")!(event, {});
    assert.equal(accepted, "ordinary work");
    assert.equal(first, undefined, "structured prompt mutation needs no custom message");
    assert.equal(Object.keys(options.sections).length, 2);
    assert.match((options.sections as Record<string, string>).goal_capability!, /explicitly asks for a persistent goal/);
    assert.doesNotMatch((options.sections as Record<string, string>).goal_capability!, /runtime state|already running/);
  });
  results.push("ok Capability notes require an explicit persistent Goal request");
  await observeScenario("Goal context enters once at run start", async () => {
    const options = { sections: { other: "Existing guideline" } };
    const event = { messageType: "user", prompt: "ordinary work", systemPrompt: "Original system", systemPromptOptions: options };
    await handlers.get("before_agent_start")!(event, {});
    const secondOptions = { sections: { other: "Another extension" } };
    await handlers.get("before_agent_start")!({ ...event, systemPromptOptions: secondOptions }, {});
    assert.equal(Object.keys(secondOptions.sections).length, 2);
    assert.equal(Object.keys(options.sections).length, 2);
  });
  results.push("ok Goal context enters once at run start");
  await observeScenario("Custom startup preserves revision authorization and clears removed state", async () => {
    focused = normalizeGoalRecord({id:"fixture",objective:"Current objective",status:"paused"});
    GoalCore.prototype.requestGoalActivation.call(activation as unknown as GoalCore, "Revision request");
    const customOptions = { sections: {} as Record<string, string> };
    await handlers.get("before_agent_start")!({messageType:"custom", message:{content:"Checkpoint"}, systemPromptOptions:customOptions}, {});
    assert.ok(activation.pendingSetting, "custom startup must preserve pending revision authorization");
    await handlers.get("message_start")!({message:{role:"custom",customType:GOAL_PROCEDURE_ENTRY,content:"Revision request"}}, {});
    assert.equal(activation.activationGoalId, "fixture", "delivered procedure activates the exact pending revision");
    assert.match(customOptions.sections.goal_runtime!, /Current objective/);
    assert.match(customOptions.sections.goal_capability!, /already has a goal/);
    focused = undefined;
    await handlers.get("before_agent_start")!({messageType:"user", prompt:"ordinary work", systemPromptOptions:customOptions}, {});
    assert.equal("goal_runtime" in customOptions.sections, false);
  });
  results.push("ok Custom startup preserves revision authorization and clears removed state");
} catch (error) {
  results.push(`FAIL ${error}`);
  process.exitCode = 1;
}
process.stdout.write(`${JSON.stringify(results)}\n`);
if (process.env.PI_E2E_ASSERTION_PATH) writeFileSync(process.env.PI_E2E_ASSERTION_PATH, JSON.stringify(observedScenarios()));
