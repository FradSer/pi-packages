"""Root provider hints must preserve Pi v1 validation and normalization."""
import pytest

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


@pytest.fixture(scope="module")
def compatibility() -> dict[str, object]:
    return run_typescript(RUNTIME_HARNESS + '''
        import { Type } from "typebox";
        import { Value } from "typebox/value";
        import { validateToolArguments } from "@earendil-works/pi-ai";
        const r = runtime();
        const result = { count: 0, valueDifferences: 0, piDifferences: 0,
            nonNullableDifferences: 0, examples: [] };
        const values = [undefined, "implement", "", null, false, 0, 0.5, [], {}];
        function validate(tool, arguments_) {
            try { return { accepted: true, arguments: validateToolArguments(tool,
                { name: tool.name, arguments: arguments_ }) }; }
            catch { return { accepted: false }; }
        }
        for (const name of ["matt_pocock_workflow", "matt_pocock_active"]) {
            const tool = r.tools.get(name);
            const original = { ...tool, parameters: Type.Union(tool.parameters.anyOf) };
            const brokenParameters = structuredClone(tool.parameters);
            for (const [field, schema] of Object.entries(brokenParameters.properties)) {
                if (schema.anyOf) brokenParameters.properties[field] =
                    schema.anyOf.find(branch => branch.type !== "null");
            }
            const broken = { ...tool, parameters: brokenParameters };
            const gateway = name === "matt_pocock_workflow";
            const fields = gateway ? ["mode", "route", "capability", "reference"]
                : ["action", "target", "reference", "reason"];
            const choices = gateway ? ["workflow", "capability", "reference"]
                : ["transition", "load", "complete", "cancel"];
            const pools = fields.map((field, i) => i === 0
                ? [undefined, ...choices, "wrong", null, false, 0, 0.5, [], {}]
                : field === "route" ? [undefined, "hard-bug", "wrong", ...values.slice(2)]
                : field === "capability" ? [undefined, "tdd", "teach", "wrong", ...values.slice(2)]
                : values);
            function compare(arguments_) {
                result.count++;
                if (Value.Check(original.parameters, arguments_) !==
                    Value.Check(tool.parameters, arguments_)) result.valueDifferences++;
                const expected = JSON.stringify(validate(original, arguments_));
                const actual = JSON.stringify(validate(tool, arguments_));
                if (expected !== actual) {
                    result.piDifferences++;
                    if (result.examples.length < 3) result.examples.push({ name, arguments_ });
                }
                if (expected !== JSON.stringify(validate(broken, arguments_)))
                    result.nonNullableDifferences++;
            }
            function expand(index, arguments_) {
                if (index === fields.length) {
                    compare(arguments_);
                    compare({ ...arguments_, extra: "undeclared" });
                    return;
                }
                for (const value of pools[index]) expand(index + 1, value === undefined
                    ? arguments_ : { ...arguments_, [fields[index]]: value });
            }
            for (const root of [null, false, 0, 0.5, "text", [], {}]) compare(root);
            expand(0, {});
        }
        console.log(JSON.stringify(result));
    ''')


def test_pi_acceptance_and_normalized_arguments_remain_equivalent(compatibility) -> None:
    """Given root hints, Pi accepts and normalizes exactly the original branches."""
    assert compatibility["count"] > 5_000
    assert compatibility["valueDifferences"] == 0
    assert compatibility["piDifferences"] == 0, compatibility["examples"]


def test_matrix_detects_optional_null_deletion_without_nullable_hints(compatibility) -> None:
    assert compatibility["nonNullableDifferences"] > 0
