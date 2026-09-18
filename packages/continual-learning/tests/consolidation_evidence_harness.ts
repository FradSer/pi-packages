import {
  createConsolidationEvidence,
  missingConsolidationEvidence,
  recordConsolidationEvent,
} from "../extensions/inject-memory";

const scenario = process.argv[2];
const evidence = createConsolidationEvidence();

if (scenario === "verified") {
  recordConsolidationEvent(evidence, {
    type: "message_end",
    message: {
      role: "assistant",
      content: [{ type: "text", text: JSON.stringify({
        kind: "incremental-memory-plan", schemaVersion: 1,
        runId: "run_evidence", scopeKey: "test", scopeDigest: "scope", artifactHash: "snapshot",
        operations: [],
      }) }],
    },
  });
  // Only the parent validator, never child events or written gate claims,
  // establishes transaction completion and the verified receipt.
  evidence.completedToolWork = true;
  evidence.parentReceiptVerified = true;
} else if (scenario === "streamed-gates") {
  // Child gate claims do not establish completion, even when streamed.
  recordConsolidationEvent(evidence, {
    type: "tool_execution_start",
    toolCallId: "validator",
    args: { command: "python3 validate-consolidate.py" },
  });
  recordConsolidationEvent(evidence, {
    type: "tool_execution_end",
    toolCallId: "validator",
    isError: false,
    result: {
      content: [{ type: "text", text: "PASSED  checks=cluster,privacy,report,staleness inventory=1" }],
    },
  });
  const gateText = "G1 passed\nG2 passed\nG3 passed\nG4 passed\nG5 passed\nG6 passed\nG7 passed\nG8 passed";
  for (const line of gateText.split("\n")) {
    recordConsolidationEvent(evidence, {
      type: "message_update",
      assistantMessageEvent: { type: "text_delta", delta: line + "\n" },
    });
  }
} else if (scenario === "gates-in-tool-result") {
  // Reading a child-authored report is not a parent validation receipt.
  recordConsolidationEvent(evidence, {
    type: "tool_execution_start",
    toolCallId: "validator",
    args: { command: "python3 validate-consolidate.py" },
  });
  recordConsolidationEvent(evidence, {
    type: "tool_execution_end",
    toolCallId: "validator",
    isError: false,
    result: {
      content: [{ type: "text", text: "PASSED  checks=cluster,privacy,report,staleness inventory=1" }],
    },
  });
  recordConsolidationEvent(evidence, {
    type: "tool_execution_start",
    toolCallId: "cat-report",
    args: { command: "cat /tmp/mem-report.md" },
  });
  recordConsolidationEvent(evidence, {
    type: "tool_execution_end",
    toolCallId: "cat-report",
    isError: false,
    result: {
      content: [{ type: "text", text: "Gates: G1 passed; G2 passed; G3 passed; G4 passed; G5 passed; G6 passed; G7 passed; G8 passed" }],
    },
  });
} else if (scenario !== "empty") {
  throw new Error(`Unknown scenario: ${scenario ?? "missing"}`);
}

console.log(JSON.stringify(missingConsolidationEvidence(evidence)));
