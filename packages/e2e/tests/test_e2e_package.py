from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"


def run_typescript(script: str) -> dict[str, object]:
    """Runs a TypeScript snippet against the package core and reads its JSON line."""
    # The snippet goes to a real file: Node does not apply a loader to stdin,
    # so `node --input-type=module` would hand the types straight to the parser.
    with tempfile.TemporaryDirectory() as folder:
        entry = Path(folder) / "snippet.mts"
        entry.write_text(textwrap.dedent(script), encoding="utf-8")
        result = subprocess.run(
            (["node", str(entry)] if os.environ.get("PI_E2E_NATIVE_TYPES") == "1" else ["node", "--import", "tsx", str(entry)]),
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    assert result.returncode == 0, f"TypeScript check failed:\n{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


PREAMBLE = f"""
import {{ readFileSync }} from "node:fs";
import {{ parseFeature, firstScenario, thenClauses, setupClauses }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
import {{ verifyScenario }} from {json.dumps((SRC / "verify.ts").as_uri())};
import {{ buildRequest }} from {json.dumps((SRC / "questions.ts").as_uri())};
import {{ injectE2ECapabilityNote, E2E_CAPABILITY_NOTE }} from {json.dumps((SRC / "presence.ts").as_uri())};
import {{ executeE2EVerify, E2E_VERIFY_PARAMS }} from {json.dumps((SRC / "tool.ts").as_uri())};
import {{ E2EGate }} from {json.dumps((SRC / "harness.ts").as_uri())};
const feature = parseFeature(readFileSync({json.dumps(str(PACKAGE / "examples" / "billing.feature"))}, "utf-8"));
const scenario = firstScenario(feature);
const evidence = JSON.parse(readFileSync({json.dumps(str(PACKAGE / "examples" / "billing-evidence.json"))}, "utf-8"));
const out = (value: unknown): void => console.log(JSON.stringify(value));
"""


def test_package_manifest_ships_the_core_and_the_feature_contract() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    for entry in ("index.ts", "src", "extensions", "features"):
        assert entry in manifest["files"]
    assert manifest["dependencies"]["@fradser/pi-kit"].startswith("workspace:")
    assert (PACKAGE / "features" / "e2e.feature").is_file()
    assert (PACKAGE / "index.ts").is_file()
    assert (PACKAGE / "AGENTS.md").is_file()
    assert (PACKAGE / "LICENSE").is_file()


def test_parse_numbers_then_clauses_and_keeps_setup_as_context() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        out({
          clauses: thenClauses(scenario).map((clause) => [clause.index, clause.text]),
          kinds: scenario.clauses.map((clause) => clause.kind),
        });
        """
    )
    assert result["clauses"] == [
        [1, "the workspace plan is Pro"],
        [2, "the billing page shows an amount that covers only the remaining days of the current billing period"],
        [3, "the payment method on file is charged exactly once"],
        [4, "no seat is lost"],
    ]
    assert result["kinds"] == ["given", "when", "then", "then", "then", "then"]


def test_declared_checks_are_asked_no_question_and_decided_in_code() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const offline = await verifyScenario({ scenario, evidence, offline: true });
        out({
          asked: offline.asked,
          clause1: offline.verdict.clauses[0],
          model: offline.verdict.model ?? null,
        });
        """
    )
    assert result["asked"] == []
    assert result["model"] is None
    clause1 = result["clause1"]
    assert isinstance(clause1, dict)
    assert clause1["status"] == "met"
    assert clause1["source"] == "deterministic"


def test_only_clauses_without_a_check_reach_the_model_request() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const request = buildRequest(scenario, evidence, [2, 3, 4]);
        out({
          ids: Object.keys(request.questions),
          types: Object.values(request.questions).map((question) => question.type),
          stateThen: (request.state.scenario as { then: unknown[] }).then,
          hasObservations: Boolean((request.state.run as { observations?: unknown }).observations),
        });
        """
    )
    assert result["ids"] == ["clause_2", "clause_3", "clause_4", "verdict", "severity", "triage_proration_wrong", "triage_duplicate_charge", "triage_seat_loss"]
    assert result["types"] == ["noul", "noul", "noul", "choice", "score", "noul", "noul", "noul"]
    assert len(result["stateThen"]) == 4
    assert result["hasObservations"] is True


def test_offline_run_reports_unverified_instead_of_claiming_fulfillment() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const { verdict } = await verifyScenario({ scenario, evidence, offline: true });
        out({
          status: verdict.status,
          exitCode: verdict.exitCode,
          reason: verdict.reason,
          unjudged: verdict.unjudged,
          sources: verdict.clauses.map((clause) => clause.source),
        });
        """
    )
    assert result["status"] == "needs_review"
    assert result["exitCode"] == 2
    assert result["unjudged"] == 3
    assert result["sources"] == ["deterministic", "none", "none", "none"]
    assert "no settled evidence" in str(result["reason"])


def test_stubbed_model_answers_decide_the_remaining_clauses_in_code() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const answers = {
          clause_2: { type: "noul", noul: 0.97 },
          clause_3: { type: "noul", noul: 0.96 },
          clause_4: { type: "noul", noul: 0.95 },
          verdict: { type: "choice", choice: "fulfilled", probabilities: { fulfilled: 0.96 }, confidence: 0.94 },
          severity: { type: "score", score: 0.07, legend: { "0": "no harm", "1": "reversible", "2": "charged" }, probabilities: { "0": 0.94, "1": 0.06 }, confidence: 0.9 },
          triage_proration_wrong: { type: "noul", noul: 0.04 },
        };
        const stub = async (): Promise<Response> =>
          new Response(JSON.stringify({ model: "jev-stub", answers, usage: { input_tokens: 1200, output_tokens: 90 } }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        const { verdict, asked, modelError } = await verifyScenario({
          scenario,
          evidence,
          client: { apiKey: "test-key", fetchImpl: stub as unknown as typeof fetch },
        });
        out({
          status: verdict.status,
          exitCode: verdict.exitCode,
          model: verdict.model,
          modelError: modelError ?? null,
          askedCount: asked.length,
          severity: verdict.severity,
          triage: verdict.triage,
          sources: verdict.clauses.map((clause) => clause.source),
          scores: verdict.clauses.map((clause) => clause.score ?? null),
        });
        """
    )
    assert result["status"] == "fulfilled"
    assert result["exitCode"] == 0
    assert result["model"] == "jev-stub"
    assert result["modelError"] is None
    assert result["askedCount"] == 8
    assert result["sources"] == ["deterministic", "jev", "jev", "jev"]
    assert result["scores"] == [1, 0.97, 0.96, 0.95]
    assert result["triage"] == [{"id": "proration_wrong", "noul": 0.04}]
    severity = result["severity"]
    assert isinstance(severity, dict)
    assert severity["level"] == 0


def test_deterministic_failure_overrides_a_fulfilled_model_verdict() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const wrong = { ...evidence, checks: [{ clause: 1, op: "equals", path: "workspace.plan", value: "enterprise" }] };
        const answers = {
          clause_2: { type: "noul", noul: 0.99 },
          clause_3: { type: "noul", noul: 0.99 },
          clause_4: { type: "noul", noul: 0.99 },
          verdict: { type: "choice", choice: "fulfilled", probabilities: { fulfilled: 0.99 }, confidence: 0.97 },
          severity: { type: "score", score: 0.0, legend: {}, probabilities: { "0": 1.0 }, confidence: 0.9 },
        };
        const stub = async (): Promise<Response> =>
          new Response(JSON.stringify({ model: "jev-stub", answers }), { status: 200 });
        const { verdict } = await verifyScenario({
          scenario,
          evidence: wrong,
          client: { apiKey: "test-key", fetchImpl: stub as unknown as typeof fetch },
        });
        out({ status: verdict.status, exitCode: verdict.exitCode, reason: verdict.reason });
        """
    )
    assert result["status"] == "not_fulfilled"
    assert result["exitCode"] == 1
    assert "deterministic check failed for clause 1" in str(result["reason"])


def test_low_model_confidence_becomes_review_not_a_pass() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const answers = {
          clause_2: { type: "noul", noul: 0.99 },
          clause_3: { type: "noul", noul: 0.99 },
          clause_4: { type: "noul", noul: 0.99 },
          verdict: { type: "choice", choice: "fulfilled", probabilities: { fulfilled: 0.52, unverified: 0.48 }, confidence: 0.51 },
          severity: { type: "score", score: 0.1, legend: {}, probabilities: { "0": 0.9 }, confidence: 0.5 },
        };
        const stub = async (): Promise<Response> =>
          new Response(JSON.stringify({ model: "jev-stub", answers }), { status: 200 });
        const { verdict } = await verifyScenario({
          scenario,
          evidence,
          client: { apiKey: "test-key", fetchImpl: stub as unknown as typeof fetch },
        });
        out({ status: verdict.status, exitCode: verdict.exitCode, reason: verdict.reason, modelVerdict: verdict.modelVerdict });
        """
    )
    assert result["status"] == "needs_review"
    assert result["exitCode"] == 2
    assert "below the verdict gate" in str(result["reason"])
    model_verdict = result["modelVerdict"]
    assert isinstance(model_verdict, dict)
    assert model_verdict["choice"] == "fulfilled"
    assert model_verdict["probability"] == 0.52


def test_html_report_marks_the_verdict_and_every_clause_row() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const { renderHtml } = await import(%s);
        out({ html: renderHtml({
          feature: "F",
          scenario: "S",
          status: "needs_review",
          exitCode: 2,
          reason: "r",
          policy: { clauseGate: 0.8, verdictGate: 0.6 },
          clauses: [
            { clause: 1, kind: "then", text: "a", status: "met", source: "deterministic", score: 1 },
            { clause: 2, kind: "then", text: "b", status: "unjudged", source: "none" },
          ],
          unjudged: 1,
          triage: [],
        }) });
        """
        % json.dumps((SRC / "report.ts").as_uri())
    )
    html = str(result["html"])
    assert 'data-testid="verdict-status">needs_review<' in html
    assert 'data-testid="clause-row"' in html
    assert html.count('data-testid="clause-row"') == 2
    assert 'data-testid="unjudged-count">1<' in html


def test_presence_injects_stable_capability_note_into_system_prompt() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const initial = [{ role: "system", content: "main prompt" }, { role: "user", content: "hello" }];
        const injected = injectE2ECapabilityNote(initial);
        out({
          count: injected.length,
          pos1Role: injected[1].role,
          pos1Contains: injected[1].content.includes("[pi-e2e capability]"),
          pos0Content: injected[0].content,
        });
        """
    )
    assert result["count"] == 3
    assert result["pos1Role"] == "system"
    assert result["pos1Contains"] is True
    assert result["pos0Content"] == "main prompt"


def test_tool_execute_e2e_verify_returns_structured_result() -> None:
    feature_path = json.dumps(str(PACKAGE / "examples" / "billing.feature"))
    evidence_path = json.dumps(str(PACKAGE / "examples" / "billing-evidence.json"))
    result = run_typescript(
        PREAMBLE
        + f"""
        let callback: {{ featurePath?: string; baseDir?: string; scenarios?: readonly string[] }} = {{}};
        const toolResult = await executeE2EVerify({{
          feature: {feature_path},
          evidence: {evidence_path},
          offline: true,
        }}, (_verdict, featurePath, baseDir, scenarios) => {{
          callback = {{ featurePath, baseDir, scenarios }};
        }});
        out({{
          isError: toolResult.isError,
          status: toolResult.details?.status,
          clauseCount: (toolResult.details?.clauses as unknown[])?.length,
          hasMarkdownText: toolResult.content[0]?.text.includes("Workspace seat billing"),
          callback: {{
            featurePath: callback.featurePath,
            baseDir: callback.baseDir,
            scenarios: callback.scenarios,
          }},
        }});
        """
    )
    assert result["status"] == "needs_review"
    assert result["isError"] is True
    assert result["clauseCount"] == 4
    assert result["hasMarkdownText"] is True
    callback = result["callback"]
    assert isinstance(callback, dict)
    assert callback["featurePath"] == str(PACKAGE / "examples" / "billing.feature")
    assert callback["scenarios"] == ["An admin upgrades a workspace to Pro and the next invoice is prorated"]
    assert callback["baseDir"] == str(REPO)


def test_shipped_extension_runs_through_pi_boundary_with_a_bounded_checkpoint() -> None:
    result = run_typescript(
        PREAMBLE
        + f"""
        import assert from "node:assert/strict";
        import {{ ExtensionRunner }} from {json.dumps((REPO / "node_modules/@earendil-works/pi-coding-agent/dist/index.js").as_uri())};
        import e2eExtension from {json.dumps((PACKAGE / "index.ts").as_uri())};
        const handlers = new Map();
        const tools = new Map();
        const commands = new Map();
        e2eExtension({{
          on(name, handler) {{
            const group = handlers.get(name) ?? [];
            group.push(handler);
            handlers.set(name, group);
          }},
          registerTool(definition) {{ tools.set(definition.name, definition); }},
          registerCommand(name, definition) {{ commands.set(name, definition); }},
          registerMessageRenderer() {{}},
        }});
        const extension = {{ path: "e2e", handlers, tools, commands, shortcuts: new Map(), flags: new Map() }};
        const runner = new ExtensionRunner([extension], {{}}, process.cwd(), {{}}, {{}});
        const errors: string[] = [];
        runner.onError((error) => errors.push(error.error));
        const context = (entries) => ({{
          canContinue: entries.length > 0,
          contextEntries: [], contextMessages: [], llmMessages: [], pendingMessages: [],
        }});
        const toolResult = handlers.get("tool_result")[0];
        await handlers.get("input")[0]({{ text: "Update packages/e2e acceptance", source: "interactive" }}, {{ cwd: process.cwd() }});
        await toolResult({{
          type: "tool_result", toolName: "write",
          input: {{ path: "packages/e2e/features/trigger.feature" }}, content: [], isError: false,
        }}, {{ cwd: process.cwd() }});
        const first = await runner.emitBoundary(
          {{ type: "agent_before_settle", outcome: "completed" }}, context,
        );
        await handlers.get("tool_result")[0]({{
          type: "tool_result", toolName: "edit",
          input: {{ path: "packages/e2e/src/harness.ts" }}, content: [], isError: false,
        }}, {{ cwd: process.cwd() }});
        assert.equal(errors.length, 0);
        const second = await runner.emitBoundary(
          {{ type: "agent_before_settle", outcome: "completed" }}, context,
        );
        const third = await runner.emitBoundary(
          {{ type: "agent_before_settle", outcome: "completed" }}, context,
        );
        assert.equal(first.valid, true);
        assert.equal(first.continue, true);
        assert.equal(first.entries.at(-1).customType, "pi-e2e-checkpoint");
        assert.match(first.entries.at(-1).content, /Never invent test results or observations/);
        assert.equal(second.continue, true);
        assert.equal(third.continue, false);
        assert.deepEqual(errors, []);
        out({{
          firstContinue: first.continue,
          firstValid: first.valid,
          checkpoint: first.entries.at(-1).customType,
          secondContinue: second.continue,
          thirdContinue: third.continue,
          errors,
        }});
        """
    )
    assert result == {
        "firstContinue": True,
        "firstValid": True,
        "checkpoint": "pi-e2e-checkpoint",
        "secondContinue": True,
        "thirdContinue": False,
        "errors": [],
    }


def test_turn_snapshot_detects_feature_changes_outside_pi_file_tools() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import path from "node:path";
        const root = await mkdtemp(path.join(tmpdir(), "pi-e2e-feature-snapshot-"));
        try {
          const featureDir = path.join(root, "features");
          await mkdir(featureDir);
          const featurePath = path.join(featureDir, "cart.feature");
          const original = "Feature: Cart\\n  Scenario: Existing\\n    Then cart is visible\\n";
          await writeFile(featurePath, original);
          const gate = new E2EGate();
          await gate.beginTurn("Update the cart acceptance feature", root);
          gate.recordToolResult("edit", { path: "features/cart.feature" }, false, root);
          await writeFile(featurePath, "Feature: Cart\\n  Scenario: Updated\\n    Then the cart is visible\\n");
          await gate.refreshFeatureChanges(root);
          const event = {
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          };
          const result = gate.checkBeforeSettle(event as never, {} as never);

          const unchangedGate = new E2EGate();
          await unchangedGate.beginTurn("Inspect existing acceptance coverage", root);
          await unchangedGate.refreshFeatureChanges(root);
          const unchanged = unchangedGate.checkBeforeSettle(event as never, {} as never);

          await writeFile(featurePath, original);
          gate.recordToolResult("bash", { command: `cd ${root} && add features/new.feature` }, false, root);
          const addedPath = path.join(featureDir, "new.feature");
          await writeFile(addedPath, "Feature: New\\n  Scenario: Added\\n    Then it works\\n");
          await gate.refreshFeatureChanges(root);
          const added = gate.checkBeforeSettle(event as never, {} as never);

          const removedGate = new E2EGate();
          await removedGate.beginTurn("Remove stale acceptance coverage", root);
          removedGate.recordToolResult("write", { path: "features/cart.feature" }, false, root);
          removedGate.recordToolResult("bash", { command: `cd ${root} && remove features/cart.feature` }, false, root);
          await rm(featurePath);
          await removedGate.refreshFeatureChanges(root);
          const removed = removedGate.checkBeforeSettle(event as never, {} as never);
          out({
            continues: result?.continue,
            namesFeature: (result?.entries[0] as { content?: string })?.content.includes(featurePath),
            unchangedContinues: unchanged?.continue ?? null,
            addedContinues: added?.continue,
            addedNamed: (added?.entries[0] as { content?: string })?.content.includes(addedPath),
            removedContinues: removed?.continue ?? null,
            noToolObservation: true,
          });
        } finally {
          await rm(root, { recursive: true, force: true });
        }
        """
    )
    assert result == {
        "continues": True,
        "namesFeature": True,
        "unchangedContinues": None,
        "addedContinues": True,
        "addedNamed": True,
        "removedContinues": True,
        "noToolObservation": True,
    }


def test_harness_gate_intercepts_unmet_verdict_before_settle() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const gate = new E2EGate();
        gate.recordToolResult("write", { path: "features/billing.feature" });
        const fakeVerdict = {
          feature: "Billing",
          scenario: "Upgrade",
          status: "needs_review",
          exitCode: 2,
          reason: "unsettled clauses",
          policy: { clauseGate: 0.8, verdictGate: 0.6 },
          clauses: [
            { clause: 1, kind: "then", text: "seats kept", status: "unjudged", source: "none" }
          ],
          unjudged: 1,
          triage: [],
        };
        gate.recordVerdict(fakeVerdict as never);

        const event = {
          type: "agent_before_settle",
          outcome: "completed",
          continue: false,
          entries: [],
          context: { pendingMessages: [] } as never,
        };
        const intervention = gate.checkBeforeSettle(event as never, {} as never);
        out({
          shouldContinue: intervention?.continue,
          entryType: intervention?.entries[0]?.type,
          customType: (intervention?.entries[0] as { customType?: string })?.customType,
          containsScenario: (intervention?.entries[0] as { content?: string })?.content.includes("Upgrade"),
        });
        """
    )
    assert result["shouldContinue"] is True
    assert result["entryType"] == "custom_message"
    assert result["customType"] == "pi-e2e-checkpoint"
    assert result["containsScenario"] is True


def test_changed_feature_starts_a_bounded_truthful_acceptance_checkpoint() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const gate = new E2EGate();
        const featurePath = "apps/shop/features/checkout.feature";
        gate.recordUserPrompt("Add checkout acceptance coverage");
        await gate.beginTurn("Add checkout acceptance coverage", process.cwd());
        gate.recordToolResult("write", { path: featurePath });
        const event = {
          type: "agent_before_settle",
          outcome: "completed",
          continue: false,
          entries: [],
          context: { pendingMessages: [] },
        };
        const notifications: Array<{ message: string; level: string }> = [];
        const context = { cwd: process.cwd() };
        const first = gate.checkBeforeSettle(event as never, context as never);
        const firstContent = (first?.entries[0] as { content?: string })?.content ?? "";
        const duplicate = gate.checkBeforeSettle(event as never, context as never);
        gate.recordToolResult("edit", { path: featurePath });
        const second = gate.checkBeforeSettle(event as never, context as never);
        const third = gate.checkBeforeSettle(event as never, context as never);
        gate.notifyOnSettled({
          ui: { notify: (message: string, level: string) => notifications.push({ message, level }) },
        } as never);
        out({
          firstContinue: first?.continue,
          namesFeature: firstContent.includes("checkout.feature"),
          inspectsProject: firstContent.includes("Inspect the current project instructions"),
          runsTests: firstContent.includes("Run the relevant existing tests"),
          truthfulEvidence: firstContent.includes("Never invent test results or observations"),
          callsVerifier: firstContent.includes("e2e_verify"),
          duplicateContinue: duplicate?.continue ?? null,
          secondContinue: second?.continue,
          thirdContinue: third?.continue ?? null,
          notification: notifications[0],
        });
        """
    )
    assert result == {
        "firstContinue": True,
        "namesFeature": True,
        "inspectsProject": True,
        "runsTests": True,
        "truthfulEvidence": True,
        "callsVerifier": True,
        "duplicateContinue": None,
        "secondContinue": True,
        "thirdContinue": None,
        "notification": {
            "message": "[e2e] waiting\nFeature: apps/shop/features/checkout.feature\nAutomatic continuation allowance exhausted.\nNext: run the remaining scenarios with the configured e2e_verify runner; report a blocker if tests cannot run.",
            "level": "warning",
        },
    }


def test_parallel_feature_change_does_not_trigger_unless_path_is_in_scope() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import path from "node:path";
        const root = await mkdtemp(path.join(tmpdir(), "pi-e2e-parallel-feature-"));
        try {
          const current = path.join(root, "packages/continual-learning/features/current.feature");
          const other = path.join(root, "packages/goal/features/goal.feature");
          await mkdir(path.dirname(current), { recursive: true });
          await mkdir(path.dirname(other), { recursive: true });
          const original = "Feature: Goal\\nScenario: Existing\\nThen goal remains\\n";
          await writeFile(other, original);
          const gate = new E2EGate();
          const taskPrompt = "Inspect tests for packages/continual-learning/src/merge.ts";
          gate.recordUserPrompt(taskPrompt, root);
          await gate.beginTurn(taskPrompt, root);
          await writeFile(other, original + "# parallel edit\\n");
          await gate.refreshFeatureChanges(root);
          const unrelated = gate.checkBeforeSettle({
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          } as never, {} as never);

          const requested = new E2EGate();
          const requestedPrompt = "Run acceptance for `packages/goal/features/goal.feature`";
          requested.recordUserPrompt(requestedPrompt, root);
          await requested.beginTurn(requestedPrompt, root);
          requested.recordToolResult("read", { path: "packages/goal/README.md" }, false, root);
          const explicit = requested.checkBeforeSettle({
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          } as never, { cwd: root } as never);
          out({
            unrelatedContinues: unrelated?.continue ?? false,
            explicitContinues: explicit?.continue ?? false,
            explicitPath: String(explicit?.entries[0]?.content).includes("packages/goal/features/goal.feature"),
          });
        } finally {
          await rm(root, { recursive: true, force: true });
        }
        """
    )
    print("parallel_feature_result", result)
    assert result == {"unrelatedContinues": False, "explicitContinues": True, "explicitPath": True}, result


def test_only_current_turn_feature_paths_are_tracked_and_explicit_paths_are_accepted() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import path from "node:path";
        const root = await mkdtemp(path.join(tmpdir(), "pi-e2e-current-feature-"));
        try {
          const currentFeature = path.join(root, "packages", "checkout", "features", "checkout.feature");
          const otherFeature = path.join(root, "packages", "goal", "features", "goal.feature");
          await mkdir(path.dirname(currentFeature), { recursive: true });
          await mkdir(path.dirname(otherFeature), { recursive: true });
          const content = "Feature: Checkout\\nScenario: Works\\nThen checkout is visible\\n";
          await writeFile(currentFeature, content);
          await writeFile(otherFeature, content);

          const untouched = new E2EGate();
          await untouched.beginTurn("Work on the checkout cart", root);
          untouched.recordToolResult("edit", { path: "packages/checkout/src/cart.ts" }, false, root);
          await writeFile(otherFeature, content + "# parallel edit\\n");
          await untouched.refreshFeatureChanges(root);
          const unrelated = untouched.checkBeforeSettle({
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          } as never, {} as never);

          const touched = new E2EGate();
          await touched.beginTurn("Update checkout", root);
          touched.recordToolResult("edit", { path: "packages/checkout/features/checkout.feature" }, false, root);
          const touchedCheckpoint = touched.checkBeforeSettle({
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          } as never, {} as never);

          const requested = new E2EGate();
          const requestedPrompt = "Run acceptance for `packages/checkout/features/checkout.feature`";
          requested.recordUserPrompt(requestedPrompt, root);
          await requested.beginTurn(requestedPrompt, root);
          requested.recordToolResult("read", { path: "packages/checkout/README.md" }, false, root);
          const requestedCheckpoint = requested.checkBeforeSettle({
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          } as never, { cwd: root } as never);
          out({
            unrelatedContinues: unrelated?.continue ?? false,
            touchedContinues: touchedCheckpoint?.continue ?? false,
            touchedPath: String(touchedCheckpoint?.entries[0]?.content).includes("packages/checkout/features/checkout.feature"),
            requestedContinues: requestedCheckpoint?.continue ?? false,
            requestedPath: String(requestedCheckpoint?.entries[0]?.content).includes("packages/checkout/features/checkout.feature"),
          });
        } finally {
          await rm(root, { recursive: true, force: true });
        }
        """
    )
    assert result == {
        "unrelatedContinues": False,
        "touchedContinues": True,
        "touchedPath": True,
        "requestedContinues": True,
        "requestedPath": True,
    }


def test_same_package_implementation_activity_does_not_select_a_feature() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import path from "node:path";
        const root = await mkdtemp(path.join(tmpdir(), "pi-e2e-package-scope-"));
        try {
          const featurePath = path.join(root, "packages/checkout/features/checkout.feature");
          await mkdir(path.dirname(featurePath), { recursive: true });
          const original = "Feature: Checkout\\nScenario: Works\\nThen checkout is visible\\n";
          await writeFile(featurePath, original);
          const gate = new E2EGate();
          await gate.beginTurn("Update the checkout implementation", root);
          gate.recordToolResult("edit", { path: "packages/checkout/src/cart.ts" }, false, root);
          await writeFile(featurePath, original + "# unrelated concurrent edit\\n");
          await gate.refreshFeatureChanges(root);
          const unrelated = gate.checkBeforeSettle({
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          } as never, { cwd: root } as never);

          const touched = new E2EGate();
          await touched.beginTurn("Run acceptance for checkout", root);
          touched.recordToolResult("write", { path: "packages/checkout/features/checkout.feature" }, false, root);
          await writeFile(featurePath, original + "# feature path named by command\\n");
          await touched.refreshFeatureChanges(root);
          const checkpoint = touched.checkBeforeSettle({
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          } as never, { cwd: root } as never);
          out({ unrelated: unrelated?.continue ?? false, touched: checkpoint?.continue ?? false });
        } finally {
          await rm(root, { recursive: true, force: true });
        }
        """
    )
    assert result == {"unrelated": False, "touched": True}


def test_repeated_settlement_requires_relevant_progress_for_a_new_checkpoint() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const gate = new E2EGate();
        gate.recordToolResult("write", { path: "features/checkout.feature" });
        const event = {
          type: "agent_before_settle", outcome: "completed", continue: false,
          entries: [], context: { pendingMessages: [] },
        };
        const first = gate.checkBeforeSettle(event as never, {} as never);
        const duplicate = gate.checkBeforeSettle(event as never, {} as never);
        gate.recordToolResult("read", { path: "packages/goal/README.md" });
        const afterUnrelatedRead = gate.checkBeforeSettle(event as never, {} as never);
        gate.recordToolResult("bash", { command: "cd apps/shop && pnpm test -- features/checkout.feature" });
        const afterFeatureMention = gate.checkBeforeSettle(event as never, {} as never);
        gate.recordToolResult("edit", { path: "features/checkout.feature" });
        const afterProgress = gate.checkBeforeSettle(event as never, {} as never);
        out({
          first: first?.continue ?? false,
          duplicate: duplicate?.continue ?? false,
          afterUnrelatedRead: afterUnrelatedRead?.continue ?? false,
          afterFeatureMention: afterFeatureMention?.continue ?? false,
          afterProgress: afterProgress?.continue ?? false,
          continuationNumbers: [first, afterProgress].map((item) =>
            Number((item?.entries[0] as { details?: { continuation?: number } })?.details?.continuation ?? 0)),
        });
        """
    )
    assert result == {
        "first": True,
        "duplicate": False,
        "afterUnrelatedRead": False,
        "afterFeatureMention": False,
        "afterProgress": True,
        "continuationNumbers": [1, 2],
    }


def test_harness_checkpoint_text_is_not_treated_as_a_user_acceptance_request() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        import { mkdtemp, rm } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import path from "node:path";
        const root = await mkdtemp(path.join(tmpdir(), "pi-e2e-self-prompt-"));
        try {
          const text = "[e2e feature acceptance checkpoint] packages/e2e/features/e2e.feature Call e2e_verify with runner. Acceptance correction 1/2.";
          const gate = new E2EGate();
          gate.recordUserPrompt(text, root);
          await gate.beginTurn(text, root);
          const event = {
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          };
          const checkpoint = gate.checkBeforeSettle(event as never, { cwd: root } as never);
          out({ continues: checkpoint?.continue ?? null });
        } finally {
          await rm(root, { recursive: true, force: true });
        }
        """
    )
    assert result == {"continues": None}, result


def test_naming_a_feature_in_a_shell_command_is_not_a_change() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import path from "node:path";
        const root = await mkdtemp(path.join(tmpdir(), "pi-e2e-shell-mention-"));
        try {
          const NL = String.fromCharCode(10);
          const feature = path.join(root, "packages/e2e/features/e2e.feature");
          await mkdir(path.dirname(feature), { recursive: true });
          const original = ["Feature: Probe", "Scenario: Probe", "Then probe holds"].join(NL) + NL;
          await writeFile(feature, original);
          const event = {
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          };

          // Naming the feature in a command only involves it.
          const named = new E2EGate();
          await named.beginTurn("Run the linked behavior tests", root);
          named.recordToolResult("bash", {
            command: "node tool.mjs packages/e2e/features/e2e.feature",
          }, false, root);
          await named.refreshFeatureChanges(root);
          const namedCheckpoint = named.checkBeforeSettle(event as never, { cwd: root } as never);

          // A real content change still starts acceptance.
          const edited = new E2EGate();
          await edited.beginTurn("Run the linked behavior tests", root);
          edited.recordToolResult("bash", {
            command: "node tool.mjs packages/e2e/features/e2e.feature",
          }, false, root);
          await writeFile(feature, original + "# changed" + NL);
          await edited.refreshFeatureChanges(root);
          const editedCheckpoint = edited.checkBeforeSettle(event as never, { cwd: root } as never);
          out({
            namedContinues: namedCheckpoint?.continue ?? null,
            editedContinues: editedCheckpoint?.continue ?? null,
            editedNamesFeature: String(editedCheckpoint?.entries[0]?.content).includes("packages/e2e/features/e2e.feature"),
          });
        } finally {
          await rm(root, { recursive: true, force: true });
        }
        """
    )
    assert result == {
        "namedContinues": None,
        "editedContinues": True,
        "editedNamesFeature": True,
    }, result


def test_shell_feature_paths_ignore_unexpanded_variables_and_keep_literal_paths() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import path from "node:path";
        const root = await mkdtemp(path.join(tmpdir(), "pi-e2e-shell-paths-"));
        try {
          const NL = String.fromCharCode(10);
          const feature = path.join(root, "packages/e2e/features/e2e.feature");
          await mkdir(path.dirname(feature), { recursive: true });
          const original = ["Feature: Probe", "Scenario: Probe", "Then probe holds"].join(NL) + NL;
          await writeFile(feature, original);
          const event = {
            type: "agent_before_settle", outcome: "completed", continue: false,
            entries: [], context: { pendingMessages: [] },
          };

          const expanded = new E2EGate();
          await expanded.beginTurn("Run the linked behavior tests", root);
          expanded.recordToolResult("bash", {
            command: `PI_E2E_FEATURE_PATH="$PWD/packages/e2e/features/e2e.feature" node tool.mjs`,
          }, false, root);
          await writeFile(feature, original + "# changed" + NL);
          await expanded.refreshFeatureChanges(root);
          const changed = expanded.checkBeforeSettle(event as never, { cwd: root } as never);
          const content = String(changed?.entries[0]?.content ?? "");

          out({
            continues: changed?.continue ?? null,
            phantomNamed: content.includes("PWD/"),
            realPathNamed: content.includes("packages/e2e/features/e2e.feature"),
          });
        } finally {
          await rm(root, { recursive: true, force: true });
        }
        """
    )
    assert result == {"continues": True, "phantomNamed": False, "realPathNamed": True}, result


def test_settled_notification_does_not_repeat_without_new_progress() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const gate = new E2EGate();
        const notifications: Array<{ message: string; level: string }> = [];
        const ctx = { ui: { notify: (message: string, level: string) => notifications.push({ message, level }) } };
        gate.recordToolResult("write", { path: "features/checkout.feature" });
        gate.notifyOnSettled(ctx as never);
        gate.notifyOnSettled(ctx as never);
        gate.notifyOnSettled(ctx as never);
        gate.recordToolResult("write", { path: "features/checkout.feature" });
        gate.notifyOnSettled(ctx as never);
        out({ count: notifications.length, levels: notifications.map((item) => item.level) });
        """
    )
    assert result == {"count": 2, "levels": ["warning", "warning"]}, result


def test_unrelated_or_failed_writes_do_not_start_feature_acceptance() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const event = {
          type: "agent_before_settle",
          outcome: "completed",
          continue: false,
          entries: [],
          context: { pendingMessages: [] },
        };
        const unrelated = new E2EGate();
        unrelated.recordToolResult("write", { path: "src/checkout.ts" });
        const failedWrite = new E2EGate();
        failedWrite.recordToolResult("write", { path: "features/checkout.feature" }, true);
        out({
          unrelated: unrelated.checkBeforeSettle(event as never, {} as never)?.continue ?? null,
          failedWrite: failedWrite.checkBeforeSettle(event as never, {} as never)?.continue ?? null,
        });
        """
    )
    assert result == {"unrelated": None, "failedWrite": None}


def test_unproven_verdicts_stay_pending_and_new_user_turn_clears_checkpoint() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const event = {
          type: "agent_before_settle",
          outcome: "completed",
          continue: false,
          entries: [],
          context: { pendingMessages: [] },
        };
        const fulfilled = {
          feature: "Checkout",
          scenario: "Upgrade",
          status: "fulfilled",
          exitCode: 0,
          reason: "verified",
          policy: { clauseGate: 0.8, verdictGate: 0.6 },
          clauses: [],
          unjudged: 0,
          triage: [],
        };
        const verified = new E2EGate();
        verified.recordToolResult("write", { path: "features/checkout.feature" });
        verified.recordVerdict(fulfilled as never, "features/checkout.feature", process.cwd(), ["Upgrade"]);
        const failedVerification = new E2EGate();
        failedVerification.recordToolResult("write", { path: "features/checkout.feature" });
        failedVerification.recordVerdict({ ...fulfilled, status: "needs_review", exitCode: 2 } as never, "features/checkout.feature", process.cwd(), ["Upgrade"]);
        const nextTurn = new E2EGate();
        nextTurn.recordToolResult("write", { path: "features/checkout.feature" });
        nextTurn.recordUserPrompt("Now work on the unrelated settings page");
        const multiple = new E2EGate();
        multiple.recordToolResult("write", { path: "features/checkout.feature" });
        multiple.recordVerdict(fulfilled as never, "features/checkout.feature", process.cwd(), ["Upgrade", "Downgrade"]);
        const stillPending = multiple.checkBeforeSettle(event as never, {} as never);
        multiple.recordVerdict({ ...fulfilled, scenario: "Downgrade" } as never, "features/checkout.feature", process.cwd(), ["Upgrade", "Downgrade"]);
        const allScenariosFulfilled = multiple.checkBeforeSettle(event as never, {} as never);
        out({
          verified: verified.checkBeforeSettle(event as never, {} as never)?.continue ?? null,
          failedVerification: failedVerification.checkBeforeSettle(event as never, {} as never)?.continue ?? null,
          nextTurn: nextTurn.checkBeforeSettle(event as never, {} as never)?.continue ?? null,
          multipleScenariosContinue: stillPending?.continue,
          allScenarios: allScenariosFulfilled?.continue ?? null,
        });
        """
    )
    assert result == {
        "verified": True,
        "failedVerification": True,
        "nextTurn": None,
        "multipleScenariosContinue": True,
        "allScenarios": True,
    }


def test_feature_path_matching_uses_the_tool_and_verifier_working_directory() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const event = {
          type: "agent_before_settle", outcome: "completed", continue: false,
          entries: [], context: { pendingMessages: [] },
        };
        const gate = new E2EGate();
        gate.recordToolResult("write", { path: "features/checkout.feature" }, false, "/project");
        gate.recordVerdict({
          feature: "Checkout", scenario: "Upgrade", status: "fulfilled", exitCode: 0,
          reason: "verified", policy: { clauseGate: 0.8, verdictGate: 0.6 },
          clauses: [], unjudged: 0, triage: [],
        } as never, "features/checkout.feature", "/other-project", ["Upgrade"]);
        out({ continues: gate.checkBeforeSettle(event as never, {} as never)?.continue ?? null });
        """
    )
    assert result == {"continues": True}


def test_boundary_does_not_duplicate_an_existing_continuation_or_pending_input() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const gate = new E2EGate();
        gate.recordToolResult("write", { path: "features/checkout.feature" });
        const continuing = {
          type: "agent_before_settle", outcome: "completed", continue: true,
          entries: [], context: { pendingMessages: [] },
        };
        const pending = {
          type: "agent_before_settle", outcome: "completed", continue: false,
          entries: [], context: { pendingMessages: [{ role: "user", content: "next" }] },
        };
        out({
          continuing: gate.checkBeforeSettle(continuing as never, {} as never)?.continue ?? null,
          pending: gate.checkBeforeSettle(pending as never, {} as never)?.continue ?? null,
          after: gate.checkBeforeSettle({ ...pending, context: { pendingMessages: [] } } as never, {} as never)?.continue ?? null,
        });
        """
    )
    assert result == {"continuing": None, "pending": None, "after": True}


def test_duplicate_deterministic_checks_combine_conjunctively_to_preserve_veto() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const duplicateChecks = {
          ...evidence,
          checks: [
            { clause: 1, op: "equals", path: "workspace.plan", value: "wrong" },
            { clause: 1, op: "equals", path: "workspace.plan", value: "pro" },
          ],
        };
        const offline = await verifyScenario({ scenario, evidence: duplicateChecks, offline: true });
        out({
          status: offline.verdict.status,
          exitCode: offline.verdict.exitCode,
          clause1Status: offline.verdict.clauses[0]?.status,
        });
        """
    )
    assert result["status"] == "not_fulfilled"
    assert result["exitCode"] == 1
    assert result["clause1Status"] == "unmet"


def test_all_deterministic_met_produces_fulfilled_without_model() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const allChecks = {
          run: evidence.run,
          checks: [
            { clause: 1, op: "equals", path: "workspace.plan", value: "pro" },
            { clause: 2, op: "contains", path: "billing_page_text", value: "USD 96.00" },
            { clause: 3, op: "equals", path: "payment_events[0].amount_usd", value: 96 },
            { clause: 4, op: "equals", path: "workspace.seats_assigned", value: 12 },
          ],
        };
        const offline = await verifyScenario({ scenario, evidence: allChecks, offline: true });
        out({
          status: offline.verdict.status,
          exitCode: offline.verdict.exitCode,
          reason: offline.verdict.reason,
          unjudged: offline.verdict.unjudged,
        });
        """
    )
    assert result["status"] == "fulfilled"
    assert result["exitCode"] == 0
    assert result["unjudged"] == 0
    assert "deterministic checks" in str(result["reason"])


def test_gherkin_background_steps_included_in_scenario_context() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const gherkinWithBg = `
Feature: Login with Background

  Background:
    Given the database is seeded
    And the user is an admin

  Scenario: Admin dashboard
    When the admin visits /dashboard
    Then the status is 200
`;
        const parsed = parseFeature(gherkinWithBg);
        const sc = firstScenario(parsed);
        out({
          backgroundCount: sc.background.length,
          setupCount: setupClauses(sc).length,
          setupTexts: setupClauses(sc).map(c => c.text),
        });
        """
    )
    assert result["backgroundCount"] == 2
    assert result["setupCount"] == 3
    assert result["setupTexts"] == ["the database is seeded", "the user is an admin", "the admin visits /dashboard"]


def test_feature_sections_and_rules_preserve_scope_and_scenario_order() -> None:
    import json

    goal_feature = json.dumps(str(REPO / "packages/goal/features/goal.feature"))
    tasks_feature = json.dumps(str(REPO / "packages/tasks/features/task-tool.feature"))
    result = run_typescript(
        PREAMBLE
        + f"""
        const goalContract = parseFeature(readFileSync({goal_feature}, "utf8"));
        const taskContract = parseFeature(readFileSync({tasks_feature}, "utf8"));
        const synthetic = parseFeature(`
@feature-one
Feature: First feature
  Background:
    Given feature setup

  @rule-one
  Rule: First rule
    Background:
      Given rule setup

    @scenario-one
    Scenario: First scenario
      When first action
      Then first result

    Scenario: Second scenario
      Then second result

Feature: Second feature
  @scenario-two
  Scenario: Third scenario
    Then third result
`);
        out({{
          goal: {{ features: goalContract.features.length, count: goalContract.scenarios.length, unique: new Set(goalContract.scenarios.map((item) => item.name)).size === goalContract.scenarios.length }},
          tasks: {{ features: taskContract.features.length, count: taskContract.scenarios.length, unique: new Set(taskContract.scenarios.map((item) => item.name)).size === taskContract.scenarios.length }},
          synthetic: {{
            feature: synthetic.feature,
            features: synthetic.features.map((item) => item.name),
            order: synthetic.scenarios.map((item) => item.name),
            featureTags: synthetic.scenarios[0]?.featureTags,
            rule: synthetic.scenarios[0]?.rule,
            ruleTags: synthetic.scenarios[0]?.ruleTags,
            scenarioTags: synthetic.scenarios[0]?.tags,
            featureBackground: synthetic.scenarios[0]?.featureBackground.map((item) => item.text),
            ruleBackground: synthetic.scenarios[0]?.ruleBackground.map((item) => item.text),
            combinedBackground: setupClauses(synthetic.scenarios[0]!).slice(0, 2).map((item) => item.text),
            grouped: synthetic.features[0]?.rules[0]?.scenarios.map((item) => item.name),
            disjunction: parseFeature(`Feature: Alternatives\nScenario: One accepted state\n  Given status is active\n    Or status is paused\n  When inspection runs\n  Then the objective is checked\n`).scenarios[0]?.clauses[0]?.text,
          }},
        }});
        """
    )
    assert result["goal"] == {"features": 12, "count": 179, "unique": True}
    assert result["tasks"] == {"features": 1, "count": 53, "unique": True}
    assert result["synthetic"] == {
        "feature": "First feature",
        "features": ["First feature", "Second feature"],
        "order": ["First scenario", "Second scenario", "Third scenario"],
        "featureTags": ["@feature-one"],
        "rule": "First rule",
        "ruleTags": ["@rule-one"],
        "scenarioTags": ["@feature-one", "@rule-one", "@scenario-one"],
        "featureBackground": ["feature setup"],
        "ruleBackground": ["rule setup"],
        "combinedBackground": ["feature setup", "rule setup"],
        "grouped": ["First scenario", "Second scenario"],
        "disjunction": "status is active\nOr status is paused",
    }



def test_min_confidence_gate_rejection() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const answers = {
          clause_2: { type: "noul", noul: 0.99 },
          clause_3: { type: "noul", noul: 0.99 },
          clause_4: { type: "noul", noul: 0.99 },
          verdict: { type: "choice", choice: "fulfilled", probabilities: { fulfilled: 0.95 }, confidence: 0.55 },
          severity: { type: "score", score: 0.0, legend: {}, probabilities: { "0": 1.0 }, confidence: 0.9 },
        };
        const stub = async (): Promise<Response> =>
          new Response(JSON.stringify({ model: "jev-stub", answers }), { status: 200 });
        const { verdict } = await verifyScenario({
          scenario,
          evidence,
          policy: { clauseGate: 0.8, verdictGate: 0.6, minConfidence: 0.8 },
          client: { apiKey: "test-key", fetchImpl: stub as unknown as typeof fetch },
        });
        out({ status: verdict.status, exitCode: verdict.exitCode, reason: verdict.reason });
        """
    )
    assert result["status"] == "needs_review"
    assert result["exitCode"] == 2
    assert "below the confidence gate" in str(result["reason"])
