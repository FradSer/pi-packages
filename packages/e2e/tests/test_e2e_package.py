from __future__ import annotations

import json
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
            ["node", "--import", "tsx", str(entry)],
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
        const toolResult = await executeE2EVerify({{
          feature: {feature_path},
          evidence: {evidence_path},
          offline: true,
        }});
        out({{
          isError: toolResult.isError,
          status: toolResult.details?.status,
          clauseCount: (toolResult.details?.clauses as unknown[])?.length,
          hasMarkdownText: toolResult.content[0]?.text.includes("Workspace seat billing"),
        }});
        """
    )
    assert result["status"] == "needs_review"
    assert result["isError"] is True
    assert result["clauseCount"] == 4
    assert result["hasMarkdownText"] is True


def test_harness_gate_intercepts_unmet_verdict_before_settle() -> None:
    result = run_typescript(
        PREAMBLE
        + """
        const gate = new E2EGate();
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
          context: {} as never,
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

