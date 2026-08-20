import {
  createConsolidationEvidence,
  missingConsolidationEvidence,
  recordConsolidationEvent,
} from "../extensions/inject-memory";

const scenario = process.argv[2];
const evidence = createConsolidationEvidence();

if (scenario === "verified") {
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
    type: "message_end",
    message: {
      role: "assistant",
      content: [{ type: "text", text: "G1 passed\nG2 passed\nG3 passed\nG4 passed\nG5 passed\nG6 passed\nG7 passed\nG8 passed" }],
    },
  });
} else if (scenario === "streamed-gates") {
  // Gates arrive via message_update text_delta events, not message_end
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
  // Gates appear in a tool_execution_end result (e.g. cat of report file)
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
