from pathlib import Path
import json
import re

PACKAGE = Path(__file__).resolve().parents[1]


def test_focused_topics_preserve_concrete_decisions() -> None:
    expected = {
        "layout": ["2×", "12px", "24px", "16–32px", "container", "pseudo-localization"],
        "typography": ["60–75", "1.4", "16px", "font-synthesis", "font-optical-sizing", "<bdi>"],
        "color": ["APCA", "4.5:1", "24px", "15°", "culori", "Radix", "contract"],
        "writing": ["ON state", "plural", "consequence", "placeholder", "recovery"],
    }
    for topic, values in expected.items():
        content = (PACKAGE / f"references/taste/{topic}.md").read_text()
        for value in values:
            assert value in content
        assert "accessibility.md#" in content
        for target in re.findall(r"\]\(([^)]+)\)", content):
            assert (PACKAGE / "references/taste" / target.split("#", 1)[0]).is_file()


def test_expansion_has_source_section_provenance() -> None:
    provenance = json.loads((PACKAGE / "taste-provenance.json").read_text())
    for topic in ("layout", "typography", "color", "writing"):
        prefix = f"references/taste/{topic}.md#"
        mappings = [m for m in provenance["mappings"] if any(d.startswith(prefix) for d in m["destinations"])]
        assert mappings, topic
        assert all(m["sourceSection"] and m["sha256"] and m["rationale"] for m in mappings)
    assert len(provenance["inventory"]) == 65
    assert len(provenance["mappings"]) > 93
