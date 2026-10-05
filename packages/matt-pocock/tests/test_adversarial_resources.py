from __future__ import annotations

from matt_pocock_helpers import run_typescript


def test_delivery_ids_are_canonicalized_and_unknown_history_is_dropped() -> None:
    result = run_typescript(
        """
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        const delta = resolveProcedureDelta("diagnosing-bugs", [], [
          " tight-red-loop ", "diagnosing-bugs", "tight-red-loop", "unknown-old-id",
        ]);
        console.log(JSON.stringify(delta));
        """
    )
    assert result["content"] == ""
    assert result["delivered"] == ["diagnosing-bugs"]


def test_legacy_state_without_delivery_tracking_can_transition_and_deliver() -> None:
    result = run_typescript(
        """
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";
        const legacy = {
          version: 1, workItemId: "legacy", route: "hard-bug",
          procedure: "diagnosing-bugs", phase: "feedback-loop",
          status: "active", loadedReferences: [],
        };
        const next = transitionState(legacy, "implement");
        const delta = resolveProcedureDelta(next.procedure, next.loadedReferences, next.deliveredProcedures);
        console.log(JSON.stringify({ next, delta }));
        """
    )
    assert result["next"]["deliveredProcedures"] == []
    assert "implement" in result["delta"]["delivered"]


def test_multibyte_bundle_limit_counts_utf8_bytes_and_rejects_overflow() -> None:
    result = run_typescript(
        """
        import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
        import { tmpdir } from "node:os";
        import { join } from "node:path";
        import { fileURLToPath, pathToFileURL } from "node:url";
        const sourcePackage = fileURLToPath(new URL("./packages/matt-pocock/", import.meta.url));
        const isolatedPackage = mkdtempSync(join(tmpdir(), "matt-boundary-package-"));
        cpSync(join(sourcePackage, "src"), join(isolatedPackage, "src"), { recursive: true });
        cpSync(join(sourcePackage, "procedures"), join(isolatedPackage, "procedures"), { recursive: true });
        const { MAX_PROCEDURE_BUNDLE_BYTES, resolveProcedureBundle } = await import(
          pathToFileURL(join(isolatedPackage, "src/resolver.ts")).href
        );
        const prefix = `<procedure-source id="pr" source="procedure/pr">\\n`;
        const suffix = `\\n</procedure-source>`;
        const unit = "界";
        const bodyBytes = MAX_PROCEDURE_BUNDLE_BYTES - Buffer.byteLength(prefix + suffix, "utf8");
        const bodyForBytes = (bytes) => unit.repeat(Math.floor(bytes / Buffer.byteLength(unit, "utf8")))
          + "a".repeat(bytes % Buffer.byteLength(unit, "utf8"));
        const exactBody = bodyForBytes(bodyBytes);
        const overflowBody = bodyForBytes(bodyBytes + 1);
        let exact = 0;
        let overflow = "";
        try {
          writeFileSync(join(isolatedPackage, "procedures/pr.md"), exactBody);
          exact = resolveProcedureBundle("pr").byteLength;
          writeFileSync(join(isolatedPackage, "procedures/pr.md"), overflowBody);
          try { resolveProcedureBundle("pr"); } catch (error) { overflow = String(error); }
          console.log(JSON.stringify({ exact, exactChars: exactBody.length, max: MAX_PROCEDURE_BUNDLE_BYTES, overflow }));
        } finally {
          rmSync(isolatedPackage, { recursive: true, force: true });
        }
        """
    )
    assert result["exact"] == result["max"]
    assert result["exactChars"] < result["max"]
    assert "maximum" in result["overflow"]


def test_catalog_manifest_derives_all_resource_edges_and_transition_guards() -> None:
    result = run_typescript(
        """
        import {
          findProcedure, normalizeProcedureId, procedureCatalog,
        } from "./packages/matt-pocock/src/catalog.ts";
        import {
          MAX_PROCEDURE_BUNDLE_BYTES, resolveAccessibleReference, resolveProcedureBundle,
        } from "./packages/matt-pocock/src/resolver.ts";
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";

        const errors = [];
        const closure = (id, seen = new Set()) => {
          const definition = findProcedure(id);
          if (!definition) { errors.push(`missing dependency: ${id}`); return []; }
          if (seen.has(definition.id)) return [];
          seen.add(definition.id);
          return [definition.id, ...(definition.requires ?? []).flatMap((dependency) => closure(dependency, seen))];
        };
        let aliasCount = 0;
        let disclosureCount = 0;
        let legalTransitionCount = 0;
        let illegalTransitionCount = 0;
        for (const definition of procedureCatalog) {
          const bundle = resolveProcedureBundle(definition.id);
          const expected = closure(definition.id);
          if (bundle.loaded.join("|") !== expected.join("|")) errors.push(`${definition.id}: closure order`);
          if (bundle.loaded.length !== new Set(bundle.loaded).size) errors.push(`${definition.id}: duplicate closure`);
          if (!bundle.loaded.includes(definition.id) || bundle.byteLength > MAX_PROCEDURE_BUNDLE_BYTES) {
            errors.push(`${definition.id}: invalid bundle boundary`);
          }
          for (const alias of definition.aliases ?? []) {
            aliasCount++;
            if (findProcedure(alias)?.id !== definition.id || normalizeProcedureId(`  ${alias}.md `) !== definition.id) {
              errors.push(`${definition.id}: alias ${alias}`);
            }
          }
          for (const reference of definition.discloses ?? []) {
            disclosureCount++;
            try {
              const resolved = resolveAccessibleReference(definition.id, [], reference);
              if (resolved.root !== findProcedure(reference)?.id) errors.push(`${definition.id}: disclosure ${reference}`);
            } catch (error) {
              errors.push(`${definition.id}: disclosure ${reference}: ${String(error)}`);
            }
          }
          for (const placement of definition.workflows ?? []) {
            const state = {
              version: 1, workItemId: `batch-${definition.id}`, route: placement.route,
              procedure: definition.id, phase: placement.phase, status: "active",
              loadedReferences: [], deliveredProcedures: [],
            };
            for (const target of placement.allowedNext) {
              try {
                const next = transitionState(state, target);
                legalTransitionCount++;
                if (next.procedure !== findProcedure(target)?.id) errors.push(`${definition.id}: target ${target}`);
              } catch (error) { errors.push(`${definition.id}: legal ${target}: ${String(error)}`); }
            }
            const before = JSON.stringify(state);
            let rejected = false;
            try { transitionState(state, "__adversarial-invalid-target__"); }
            catch { rejected = true; }
            illegalTransitionCount++;
            if (!rejected) errors.push(`${definition.id}: invalid transition accepted`);
            if (JSON.stringify(state) !== before) errors.push(`${definition.id}: invalid transition mutated state`);
          }
        }
        console.log(JSON.stringify({
          catalog: procedureCatalog.length, aliasCount, disclosureCount,
          legalTransitionCount, illegalTransitionCount, errors,
        }));
        """
    )
    assert result["errors"] == []
    assert result["catalog"] >= 1
    assert result["aliasCount"] >= 1
    assert result["disclosureCount"] >= 1
    assert result["legalTransitionCount"] >= 1
    assert result["illegalTransitionCount"] >= 1


def test_latest_malformed_record_does_not_resurrect_older_active_workflow() -> None:
    result = run_typescript(
        """
        import { latestWorkflowRecord } from "./packages/matt-pocock/src/workflow.ts";
        const active = {
          version: 1, workItemId: "w", route: "hard-bug", procedure: "diagnosing-bugs",
          phase: "feedback-loop", status: "active", loadedReferences: [],
        };
        const malformed = { version: 2, workItemId: "w", route: "hard-bug", procedure: "diagnosing-bugs" };
        console.log(JSON.stringify({ record: latestWorkflowRecord([
          { type: "custom", customType: "matt-pocock-workflow", data: active },
          { type: "custom", customType: "matt-pocock-workflow", data: malformed },
        ]) ?? null }));
        """
    )
    assert result["record"] is None


def test_transition_rejects_a_route_procedure_with_a_corrupted_phase() -> None:
    result = run_typescript(
        """
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";
        const state = {
          version: 1, workItemId: "corrupt", route: "hard-bug",
          procedure: "diagnosing-bugs", phase: "not-the-feedback-loop",
          status: "active", loadedReferences: [], deliveredProcedures: [],
        };
        let error = "";
        try { transitionState(state, "implement"); } catch (caught) { error = String(caught); }
        console.log(JSON.stringify({ error }));
        """
    )
    assert "invalid current procedure state" in result["error"]
