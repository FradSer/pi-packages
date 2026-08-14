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
} else if (scenario !== "empty") {
  throw new Error(`Unknown scenario: ${scenario ?? "missing"}`);
}

console.log(JSON.stringify(missingConsolidationEvidence(evidence)));
