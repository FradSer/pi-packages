from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]


def test_canonical_press_feedback_contract() -> None:
    components = (PACKAGE / "references/taste/components.md").read_text()
    assert "0.96" in components
    assert "150ms" in components or "150 ms" in components
    assert "keyboard" in components.lower()
    assert "token" in components.lower()


def test_canonical_motion_and_accessibility_contract() -> None:
    motion = (PACKAGE / "references/taste/motion.md").read_text()
    accessibility = (PACKAGE / "references/taste/accessibility.md").read_text()
    assert "interrupt" in motion.lower()
    assert "gesture" in motion.lower()
    assert "transition" in motion.lower()
    assert "reduced-motion" in accessibility.lower()
    assert "static" in accessibility.lower() or "nonspatial" in accessibility.lower()


def test_taste_provenance_maps_real_anchors_and_pending_scope() -> None:
    import json
    import re

    provenance = json.loads((PACKAGE / "taste-provenance.json").read_text())
    assert provenance["coverage"] == "first-slice"
    assert len(provenance["inventory"]) == 65
    assert any(item["disposition"] == "pending" for item in provenance["inventory"])
    assert any(item["disposition"] == "excluded" for item in provenance["inventory"])
    assert provenance["conflicts"]["press-feedback"]["selected"] == "0.96 / 150ms"
    for mapping in provenance["mappings"]:
        assert re.fullmatch(r"[a-f0-9]{64}", mapping["sha256"])
        assert mapping["sourceSection"]
        assert mapping["rationale"]
        for destination in mapping["destinations"]:
            path, anchor = destination.split("#", 1)
            content = (PACKAGE / path).read_text()
            headings = re.findall(r"^## (.+)$", content, re.MULTILINE)
            anchors = [re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings]
            assert anchor in anchors


def test_taste_scope_and_nonspatial_feedback() -> None:
    root = PACKAGE / "references/taste"
    motion = (root / "motion.md").read_text()
    assert "presentation value" in motion
    assert "release velocity" in motion
    assert "not inherently impossible to interrupt" in motion
    accessibility = (root / "accessibility.md").read_text()
    assert "prefers-reduced-motion: no-preference" in accessibility
    assert "5 seconds" in accessibility
    assert "Aria-disabled" in accessibility
    for path in root.glob("*.md"):
        import re
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            assert (path.parent / target.split("#", 1)[0]).is_file()


def test_source_mapping_selectors_match_inventory_fingerprints() -> None:
    import json

    provenance = json.loads((PACKAGE / "taste-provenance.json").read_text())
    inventory = {
        (item["source"], item["sourcePath"]): item
        for item in provenance["inventory"]
    }
    assert len(inventory) == 65
    assert sum(key[0] == "jakubkrehel" for key in inventory) == 46
    assert sum(key[0] == "emilkowalski" for key in inventory) == 19
    for mapping in provenance["mappings"]:
        item = inventory[(mapping["source"], mapping["sourcePath"])]
        assert item["sha256"] == mapping["sha256"]
        assert mapping["sourceSection"] in item["mappedSectionSelectors"]
    assert any(len(mapping["destinations"]) > 1 for mapping in provenance["mappings"])
    press_sources = {
        mapping["source"]
        for mapping in provenance["mappings"]
        if "references/taste/components.md#press-feedback" in mapping["destinations"]
    }
    assert press_sources == {"jakubkrehel", "emilkowalski"}
    assert all(item["reason"] for item in inventory.values())
