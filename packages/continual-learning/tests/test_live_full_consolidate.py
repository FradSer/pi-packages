"""Focused evidence contract for the native full consolidation fixture."""

from __future__ import annotations

from live_full_consolidate import readback_marker_ids


MARKERS = {
    "full_fact.md": "BODY_ONLY_MARKER_ALPHA_9f4c",
    "full_second.md": "BODY_ONLY_MARKER_BETA_3a71",
}
ROOT = "/tmp/full-memory"
PATHS = {"read-1": f"{ROOT}/full_fact.md", "read-2": f"{ROOT}/full_second.md"}


def test_index_or_frontmatter_text_does_not_count_as_body_readback() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "read-1", "content": "full_fact.md — settled full corpus fact"},
        {"role": "tool", "tool_call_id": "read-2", "content": "description: settled full corpus fact"},
    ]
    assert readback_marker_ids(messages, MARKERS, PATHS, ROOT) == set()


def test_wrong_tool_ids_do_not_count_as_corresponding_body_reads() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "read-2", "content": "full_fact body BODY_ONLY_MARKER_ALPHA_9f4c"},
        {"role": "tool", "tool_call_id": "read-1", "content": "full_second body BODY_ONLY_MARKER_BETA_3a71"},
    ]
    assert readback_marker_ids(messages, MARKERS, PATHS, ROOT) == set()


def test_matching_tool_ids_and_body_markers_count() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "read-1", "content": "full_fact body BODY_ONLY_MARKER_ALPHA_9f4c"},
        {"role": "tool", "tool_call_id": "read-2", "content": "full_second body BODY_ONLY_MARKER_BETA_3a71"},
    ]
    assert readback_marker_ids(messages, MARKERS, PATHS, ROOT) == {"read-1", "read-2"}


def test_missing_or_unrelated_read_call_map_is_rejected() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "read-1", "content": "BODY_ONLY_MARKER_ALPHA_9f4c"},
        {"role": "tool", "tool_call_id": "read-2", "content": "BODY_ONLY_MARKER_BETA_3a71"},
    ]
    assert readback_marker_ids(messages, MARKERS, {}, ROOT) == set()
    unrelated = {"read-1": "/unrelated/full_fact.md", "read-2": f"{ROOT}/full_second.md"}
    assert readback_marker_ids(messages, MARKERS, unrelated, ROOT) == set()
