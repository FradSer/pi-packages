"""Every JSON value class at the public tool boundary, not arbitrary JS values."""
import pytest

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


@pytest.fixture(scope="module")
def boundary_results() -> dict[str, object]:
    return run_typescript(RUNTIME_HARNESS + '''
        import { Value } from "typebox/value";
        const r = runtime();
        const values = [null, false, 0, 1.5, "text", [], {}];
        const definitions = [...r.tools.values()];
        const invalidRoots = Object.fromEntries(definitions.map(tool => [tool.name,
            values.map(value => Value.Check(tool.parameters, value))]));
        const gateway = r.tools.get("matt_pocock_workflow").parameters;
        const active = r.tools.get("matt_pocock_active").parameters;
        const ask = r.tools.get("matt_pocock_ask").parameters;
        const nonStrings = values.filter(value => typeof value !== "string");
        console.log(JSON.stringify({invalidRoots,
            targets:nonStrings.map(target=>Value.Check(active,{action:"transition",target})),
            references:nonStrings.map(reference=>Value.Check(active,{action:"load",reference})),
            routes:nonStrings.map(route=>Value.Check(gateway,{mode:"workflow",route})),
            capabilities:nonStrings.map(capability=>Value.Check(gateway,{mode:"capability",capability})),
            options:nonStrings.map(option=>Value.Check(ask,{question:"Q",options:["A",option]})),
            valid:[Value.Check(gateway,{mode:"workflow",route:"hard-bug"}),
                   Value.Check(active,{action:"transition",target:"implement"}),
                   Value.Check(active,{action:"load",reference:"LOGIC"}),
                   Value.Check(active,{action:"complete"}),
                   Value.Check(active,{action:"cancel",reason:"test"}),
                   Value.Check(ask,{question:"Q",options:["A","B"],recommended:"A"})]
        }));
    ''')


def test_every_json_root_type_is_rejected_without_required_shape(boundary_results) -> None:
    assert set(boundary_results["invalidRoots"]) == {"matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"}
    assert all(not any(values) for values in boundary_results["invalidRoots"].values())


@pytest.mark.parametrize("field", ["targets", "references", "routes", "capabilities", "options"])
def test_non_string_identifiers_and_labels_are_rejected(boundary_results, field: str) -> None:
    assert not any(boundary_results[field])


def test_valid_operation_shapes_remain_accepted(boundary_results) -> None:
    assert all(boundary_results["valid"])
