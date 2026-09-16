from __future__ import annotations

import json
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]


def run_bun(source: str) -> dict[str, object]:
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_policy_phases_and_post_execution_checks_are_explicit() -> None:
    source = r'''
      import fs from "node:fs";
      import os from "node:os";
      import path from "node:path";
      import { evaluate, evaluatePhase, mergeLayers } from "./packages/continual-learning/extensions/guardrail-engine.ts";
      import registerOutputChecks from "./packages/continual-learning/extensions/output-checks.ts";

      const hooks = {};
      const entries = [];
      const repairs = [];
      const pi = {
        on: (name, fn) => (hooks[name] ??= []).push(fn),
        appendEntry: (customType, data) => entries.push({ customType, data }),
        sendMessage: (message, options) => repairs.push({ message, options }),
        registerEntryRenderer: () => {},
      };
      const config = mergeLayers([{
        source: "project",
        policies: [
          { name: "tool-default", tools: ["bash"], paths: ["command"], pattern: "legacy-secret", reason: "Keep tool-call rule." },
          { name: "output-secret", phase: "output", pattern: "DO_NOT_SAY", reason: "Do not disclose this output." },
          { name: "artifact-secret", phase: "artifact", tools: ["write", "edit"], pattern: "DO_NOT_WRITE", reason: "Remove this artifact content." },
          { name: "bash-artifact-secret", phase: "artifact", tools: ["bash"], artifactPaths: ["generated.txt"], pattern: "DO_NOT_WRITE", reason: "Remove this command-produced content." },
        ],
      }]);
      const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guard-output-"));
      const cwd = path.join(tmp, "project");
      const agentDir = path.join(tmp, "agent");
      fs.mkdirSync(agentDir, { recursive: true });
      process.env.PI_CODING_AGENT_DIR = agentDir;
      fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });
      fs.writeFileSync(path.join(cwd, ".pi", "harness.json"), JSON.stringify({ policies: [
        { name: "output-secret", phase: "output", pattern: "DO_NOT_SAY", reason: "Do not disclose this output." },
        { name: "artifact-secret", phase: "artifact", tools: ["write", "edit"], pattern: "DO_NOT_WRITE", reason: "Remove this artifact content." },
        { name: "bash-artifact-secret", phase: "artifact", tools: ["bash"], artifactPaths: ["generated.txt"], pattern: "DO_NOT_WRITE", reason: "Remove this command-produced content." },
      ] }));
      const ctx = { cwd, hasUI: false };
      registerOutputChecks(pi);

      const defaultDecision = evaluate(config, { toolName: "bash", args: { command: "legacy-secret" } });
      const outputDecision = evaluatePhase(config, { phase: "output", text: "DO_NOT_SAY" });
      const artifactDecision = evaluatePhase(config, { phase: "artifact", toolName: "write", text: "DO_NOT_WRITE" });

      const outputHandler = hooks.message_end[0];
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }] } }, { ...ctx });
      const outputRepairsAfterFirst = repairs.length;
      hooks.input[0]({ type: "input", source: "extension", text: "extension correction" }, { ...ctx });
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }] } }, { ...ctx });
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }] } }, { ...ctx });

      hooks.input[0]({ type: "input", source: "interactive", text: "interrupted task" }, { ...ctx });
      fs.writeFileSync(path.join(cwd, "generated.txt"), "DO_NOT_WRITE");
      const repairsBeforeInterrupted = repairs.length;
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }], stopReason: "aborted" } }, { ...ctx });
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }], stopReason: "error" } }, { ...ctx });
      const interruptedDidNotRepair = repairs.length === repairsBeforeInterrupted;

      const artifactHandler = hooks.tool_result[0];
      hooks.input[0]({ type: "input", source: "interactive", text: "start a new task" }, { ...ctx });
      const safePath = path.join(cwd, "safe.txt");
      fs.writeFileSync(safePath, "safe artifact");
      await artifactHandler({ type: "tool_result", toolCallId: "1", toolName: "write", input: { path: "safe.txt", content: "DO_NOT_WRITE" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const matchingPath = path.join(cwd, "matching.txt");
      fs.writeFileSync(matchingPath, "DO_NOT_WRITE");
      await artifactHandler({ type: "tool_result", toolCallId: "2", toolName: "write", input: { path: "matching.txt", content: "safe argument" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const repairsAfterMatchingArtifact = repairs.length;
      await artifactHandler({ type: "tool_result", toolCallId: "2-repeat", toolName: "write", input: { path: "matching.txt", content: "safe argument" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const unchangedArtifactDeduped = repairs.length === repairsAfterMatchingArtifact;
      const generatedPath = path.join(cwd, "generated.txt");
      fs.writeFileSync(generatedPath, "DO_NOT_WRITE");
      await artifactHandler({ type: "tool_result", toolCallId: "bash-1", toolName: "bash", input: { command: "generate safe artifact" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const repairsBeforeUnsupported = repairs.length;
      await artifactHandler({ type: "tool_result", toolCallId: "3", toolName: "write", input: {}, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const outside = path.join(tmp, "outside.txt");
      fs.writeFileSync(outside, "DO_NOT_WRITE");
      await artifactHandler({ type: "tool_result", toolCallId: "4", toolName: "write", input: { path: "../outside.txt" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const target = path.join(cwd, "target.txt");
      fs.writeFileSync(target, "safe");
      fs.symlinkSync(target, path.join(cwd, "link.txt"));
      await artifactHandler({ type: "tool_result", toolCallId: "5", toolName: "write", input: { path: "link.txt" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const large = path.join(cwd, "large.txt");
      fs.writeFileSync(large, "x".repeat(1_000_001));
      await artifactHandler({ type: "tool_result", toolCallId: "6", toolName: "write", input: { path: "large.txt" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const unsupportedDidNotRepair = repairs.length === repairsBeforeUnsupported;
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "done" }], stopReason: "stop" } }, { ...ctx });

      console.log(JSON.stringify({
        phases: config.policies.map((policy) => [policy.name, policy.phase]),
        defaultMatchesToolCall: defaultDecision?.policyName === "tool-default",
        outputMatches: outputDecision?.policyName === "output-secret",
        artifactMatches: artifactDecision?.policyName === "artifact-secret",
        outputRepairsBounded: outputRepairsAfterFirst === 1 && entries.filter((entry) => entry.data?.phase === "output" && entry.data?.status === "violated").length === 2,
        interruptedDidNotRepair,
        unchangedArtifactDeduped,
        outputViolation: entries.some((entry) => entry.data?.phase === "output" && entry.data?.status === "violated"),
        outputExhausted: entries.some((entry) => entry.data?.phase === "output" && entry.data?.status === "repair-exhausted"),
        argsOnlyDoesNotMatchArtifact: !entries.some((entry) => entry.data?.path === "safe.txt" && entry.data?.status === "violated"),
        actualArtifactMatches: entries.some((entry) => entry.data?.path === "matching.txt" && entry.data?.status === "violated"),
        bashArtifactMatches: entries.some((entry) => entry.data?.path === "generated.txt" && entry.data?.status === "violated"),
        unsupportedMissing: entries.some((entry) => entry.data?.path === undefined && entry.data?.status === "unsupported"),
        unsupportedOutside: entries.some((entry) => entry.data?.path === "../outside.txt" && entry.data?.status === "unsupported"),
        unsupportedSymlink: entries.some((entry) => entry.data?.path === "link.txt" && entry.data?.status === "unsupported"),
        unsupportedLarge: entries.some((entry) => entry.data?.path === "large.txt" && entry.data?.status === "unsupported"),
        unsupportedDidNotRepair,
        finalArtifactRecheckDeduped: entries.filter((entry) => entry.data?.path === "matching.txt" && entry.data?.status === "violated").length === 1,
        finalBashRecheckDeduped: entries.filter((entry) => entry.data?.path === "generated.txt" && entry.data?.status === "violated").length === 1,
      }));
    '''
    result = run_bun(source)
    assert result["phases"] == [["tool-default", "tool-call"], ["output-secret", "output"], ["artifact-secret", "artifact"], ["bash-artifact-secret", "artifact"]]
    assert result["defaultMatchesToolCall"]
    assert result["outputMatches"] and result["artifactMatches"]
    assert result["outputRepairsBounded"] and result["outputViolation"] and result["outputExhausted"]
    assert result["interruptedDidNotRepair"] and result["unchangedArtifactDeduped"]
    assert result["argsOnlyDoesNotMatchArtifact"] and result["actualArtifactMatches"] and result["bashArtifactMatches"]
    assert result["unsupportedMissing"] and result["unsupportedOutside"] and result["unsupportedSymlink"] and result["unsupportedLarge"]
    assert result["unsupportedDidNotRepair"]
    assert result["finalArtifactRecheckDeduped"] and result["finalBashRecheckDeduped"]


def test_context_guidance_is_registered_separately_from_guardrail_enforcement() -> None:
    source = r'''
      import fs from "node:fs";
      import os from "node:os";
      import path from "node:path";
      import registerGuardrails from "./packages/continual-learning/extensions/guardrails.ts";
      import registerContextGuidance from "./packages/continual-learning/extensions/context-guidance.ts";

      const hooks = {};
      const entries = [];
      const pi = {
        on: (name, fn) => (hooks[name] ??= []).push(fn),
        appendEntry: (customType, data) => entries.push({ customType, data }),
        registerEntryRenderer: () => {},
        registerCommand: () => {},
        getCommands: () => [{ name: "skill:review", source: "skill" }],
      };
      const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guard-context-"));
      const cwd = path.join(tmp, "project");
      fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });
      fs.writeFileSync(path.join(cwd, ".pi", "harness.json"), JSON.stringify({ skillPrompts: { review: { prompt: "use the review checklist", target: "system" } } }));
      const event = { type: "before_agent_start", prompt: '<skill name="review" location="/tmp/review/SKILL.md">\ncheck\n</skill>', systemPrompt: "base", systemPromptOptions: {skills:[{name:"review"}]} };
      const ctx = { cwd, hasUI: false };
      registerGuardrails(pi);
      const guardrailBefore = hooks.before_agent_start?.length ?? 0;
      registerContextGuidance(pi);
      const guidanceResult = await hooks.before_agent_start[0](event, ctx);
      console.log(JSON.stringify({ guardrailBefore, guidanceResult, eventCount: entries.length }));
    '''
    result = run_bun(source)
    assert result["guardrailBefore"] == 0
    assert result["guidanceResult"]["systemPrompt"] == "base\n\nuse the review checklist"
    assert result["eventCount"] == 1


def test_post_generation_policy_rejects_retroactive_confirmation_and_wrong_subject_fields() -> None:
    source = r'''
      import { validatePolicyDeclaration } from "./packages/continual-learning/extensions/guardrail-engine.ts";
      console.log(JSON.stringify({
        output: validatePolicyDeclaration({ name: "output", phase: "output", tools: ["write"], paths: ["content"], action: "confirm", pattern: "x", reason: "x" }),
        artifact: validatePolicyDeclaration({ name: "artifact", phase: "artifact", paths: ["content"], require: { path: "path", pattern: "x" }, action: "confirm", pattern: "x", reason: "x" }),
        validArtifact: validatePolicyDeclaration({ name: "artifact-ok", phase: "artifact", tools: ["bash"], artifactPaths: ["dist/out.txt"], pattern: "x", reason: "x" }),
      }));
    '''
    result = run_bun(source)
    output_errors = " ".join(result["output"])
    artifact_errors = " ".join(result["artifact"])
    assert "confirm action is unavailable" in output_errors
    assert "tools is only supported" in output_errors
    assert "paths is only supported" in output_errors
    assert "confirm action is unavailable" in artifact_errors
    assert "paths is only supported" in artifact_errors
    assert "require.path is only supported" in artifact_errors
    assert result["validArtifact"] == []
