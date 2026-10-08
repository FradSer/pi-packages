from __future__ import annotations

from test_e2e_package import PREAMBLE, run_typescript


def test_cli_exit_codes_reports_and_invalid_inputs() -> None:
    import json
    from test_e2e_package import SRC

    result = run_typescript(PREAMBLE + f'\nimport {{main}} from {json.dumps((SRC / "cli.ts").as_uri())};\n' + r'''
      import {mkdtemp, writeFile, readFile, rm} from "node:fs/promises";
      import {tmpdir} from "node:os";
      import path from "node:path";
      const cwd = await mkdtemp(path.join(tmpdir(), "pi-e2e-cli-"));
      try {
        const feature = path.join(cwd, "test.feature");
        const evidence = path.join(cwd, "evidence.json");
        const report = path.join(cwd, "reports/report.html");
        await writeFile(feature, "Feature: <Test>\nScenario: Works\nThen value is true\n");
        const calls = [];
        for (const mode of ["pass", "fail", "unjudged"]) {
          await writeFile(evidence, JSON.stringify({run: {observations: {value: mode === "pass"}},
            ...(mode === "unjudged" ? {} : {checks: [{clause: 1, path: "value", op: "equals", value: true}]})}));
          const lines = []; const errors = [];
          const code = await main(["verify", "--feature", feature, "--evidence", evidence, "--offline", "--json", "--report-html", report], {log: line => lines.push(line), error: line => errors.push(line)});
          calls.push({code, status: JSON.parse(lines[0]).status, errors});
        }
        const invalid = await main(["verify", "--unknown"], {log: () => {}, error: () => {}});
        out({calls, invalid, escaped: (await readFile(report, "utf8")).includes("&lt;Test&gt;")});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert [call["code"] for call in result["calls"]] == [0, 1, 2]
    assert [call["status"] for call in result["calls"]] == ["fulfilled", "not_fulfilled", "needs_review"]
    assert all(call["errors"] == [] for call in result["calls"])
    assert result["invalid"] == 2
    assert result["escaped"] is True


def test_provider_http_errors_invalid_answers_and_abort_fail_closed() -> None:
    import json
    from test_e2e_package import SRC

    result = run_typescript(PREAMBLE + f'\nimport {{systemOne}} from {json.dumps((SRC / "typesafe.ts").as_uri())};\n' + r'''
      import {createServer} from "node:http";
      import {once} from "node:events";
      let mode = "401";
      const seen = [];
      const controller = new AbortController();
      const server = createServer(async (request, response) => {
        let body = ""; for await (const part of request) body += part;
        seen.push({auth: request.headers.authorization, model: JSON.parse(body).model});
        if (mode === "abort") {controller.abort(); return;}
        response.setHeader("content-type", "application/json");
        if (mode === "bad-json") response.end("{");
        else if (mode === "bad-answer") response.end(JSON.stringify({model: "test", answers: {clause_1: {type: "noul", noul: 2}}}));
        else {response.statusCode = Number(mode); response.end("{}");}
      });
      server.listen(0, "127.0.0.1"); await once(server, "listening");
      try {
        const address = server.address();
        const endpoint = `http://127.0.0.1:${address.port}`;
        const codes = [];
        for (mode of ["401", "422", "429", "529", "500", "bad-json", "bad-answer"]) {
          try {await systemOne({apiKey: "isolated-test-key", endpoint}, {state: {}, questions: {}}); codes.push("passed");}
          catch (error) {codes.push(error.code);}
        }
        mode = "abort";
        const target = firstScenario(parseFeature("Feature: Test\nScenario: Works\nThen value holds\n"));
        let aborted = false;
        try {await verifyScenario({scenario: target, evidence: {run: {observations: {}}}, signal: controller.signal,
          client: {apiKey: "isolated-test-key", endpoint}});} catch {aborted = true;}
        out({codes, aborted, auth: seen.every(item => item.auth === "Bearer isolated-test-key"), models: [...new Set(seen.map(item => item.model))]});
      } finally {server.closeAllConnections(); await new Promise(resolve => server.close(resolve));}
    ''')
    assert result["codes"] == ["UNAUTHORIZED", "INVALID_REQUEST", "RATE_LIMITED", "RATE_LIMITED", "PROVIDER_FAILED", "INVALID_RESPONSE", "INVALID_RESPONSE"]
    assert result["aborted"] is True
    assert result["auth"] is True
    assert result["models"] == ["jev-latest"]


def test_gherkin_unsupported_structures_and_prototype_paths_are_safe() -> None:
    import json
    from test_e2e_package import SRC

    result = run_typescript(PREAMBLE + f'\nimport {{resolvePath}} from {json.dumps((SRC / "checks.ts").as_uri())};\n' + r'''
      const unsupported = ["Scenario Outline: Works", "Examples:", "| value |", '"""'];
      const rejected = unsupported.map(line => {
        try {parseFeature("Feature: Test\nScenario: Works\nThen value holds\n" + line); return false;} catch {return true;}
      });
      const duplicateScenario = (() => {
        try { parseFeature("Feature: One\nScenario: Same\nThen first\nFeature: Two\nScenario: Same\nThen second\n"); return false; }
        catch { return true; }
      })();
      const lateFeatureBackground = (() => {
        try { parseFeature("Feature: One\nScenario: First\nThen first\nBackground:\n  Given late\n"); return false; }
        catch { return true; }
      })();
      const lateRuleBackground = (() => {
        try { parseFeature("Feature: One\nRule: R\nScenario: First\nThen first\nBackground:\n  Given late\n"); return false; }
        catch { return true; }
      })();
      out({rejected, duplicateScenario, lateFeatureBackground, lateRuleBackground,
        inherited: resolvePath({value: true}, "__proto__.toString") === undefined,
        indexes: resolvePath({items: [{value: 42}]}, "items[0].value")});
    ''')
    assert all(result["rejected"])
    assert result["inherited"] is True
    assert result["indexes"] == 42
