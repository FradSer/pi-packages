import json
from pathlib import Path

from live_monitor import read_trace


def test_jsonl_trace_preserves_unicode_line_separators(tmp_path: Path) -> None:
    values = [{"content": "中文\u2028下一行\u2029尾部\u0085结束"}, {"content": "next"}]
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in values) + "\n", encoding="utf-8")
    assert read_trace(trace) == values
