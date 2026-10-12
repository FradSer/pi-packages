export { default } from "./extensions/index.ts";
export { evaluateChecks, resolvePath } from "./src/checks.ts";
export { findings, nextAction } from "./src/guidance.ts";
export type { Finding, NextAction } from "./src/guidance.ts";
export { composeVerdict } from "./src/compose.ts";
export { firstScenario, GherkinError, parseFeature, scenarioByName, setupClauses, thenClauses } from "./src/gherkin.ts";
export { buildRequest, buildState, clauseId, triageId } from "./src/questions.ts";
export { renderHtml, renderMarkdown } from "./src/report.ts";
export { parseAnswers, systemOne, TypeSafeError } from "./src/typesafe.ts";
export type { ModelAnswer, ModelResponse } from "./src/typesafe.ts";
export { DEFAULT_POLICY, verifyScenario } from "./src/verify.ts";
export type { VerifyOptions, VerifyResult } from "./src/verify.ts";
export { E2E_CAPABILITY_NOTE, injectE2ECapabilityNote } from "./src/presence.ts";
export { E2EGate, registerE2EHarness } from "./src/harness.ts";
export { E2E_VERIFY_OUTPUT_SCHEMA, E2E_VERIFY_PARAMS, executeE2EVerify, registerE2ETools } from "./src/tool.ts";
export type {
  Clause,
  CheckObservation,
  ClauseResult,
  Evidence,
  FeatureFile,
  Policy,
  Scenario,
  Severity,
  Verdict,
  VerdictStatus,
} from "./src/types.ts";
