from __future__ import annotations

import json

import pytest

from test_btw_package import SRC, run_typescript


@pytest.mark.parametrize("loading", [False, True])
def test_scroll_keys_work_during_answers_and_followups(loading: bool) -> None:
    result = run_typescript(
        f"""
        import {{ createBtwOverlay, maxAnswerBody }} from {json.dumps((SRC / 'overlay.ts').as_uri())};
        const overlay = createBtwOverlay({{ terminal: {{ rows: 30, columns: 80 }}, requestRender() {{}} }}, testStyle, {{
          question: 'first', onCancel() {{}}, onSpawn() {{}}
        }});
        overlay.showAnswer(Array.from({{ length: 60 }}, (_, i) => `line-${{i}}`).join('\\n\\n'));
        if ({str(loading).lower()}) {{ overlay.handleInput('followup'); overlay.handleInput('\\r'); }}
        for (let i = 0; i < 200; i++) overlay.handleInput('\\x1b[5~');
        const top = overlay.render(80).join('\\n');
        overlay.handleInput('\\x1b[6~');
        const page = overlay.render(80).join('\\n');
        for (let i = 0; i < 200; i++) overlay.handleInput('\\x1b[6~');
        const bottom = overlay.render(80).join('\\n');
        overlay.dispose();
        console.log(JSON.stringify({{ top, page, bottom, cap: maxAnswerBody(30) }}));
        """
    )
    assert "line-0" in result["top"]
    assert result["page"] != result["top"]
    assert "line-59" in result["bottom"]
    assert result["cap"] == 12


def test_legacy_callbacks_and_initial_cancel_remain_available() -> None:
    result = run_typescript(
        f"""
        import {{ createBtwOverlay }} from {json.dumps((SRC / 'overlay.ts').as_uri())};
        const signals = [];
        let closes = 0;
        const make = () => createBtwOverlay({{ terminal: {{ rows: 40, columns: 80 }}, requestRender() {{}} }}, testStyle, {{
          question: 'legacy', onCancel: () => closes++, onSpawn: (signal) => signals.push(signal)
        }});
        const answered = make();
        answered.showAnswer('legacy answer', {{ usage: {{ totalTokens: 7, cost: 0.01 }}, elapsedMs: 1000 }});
        const answer = answered.render(80).join('\\n');
        answered.dispose();
        const failed = make();
        failed.showError('legacy failure');
        const error = failed.render(80).join('\\n');
        failed.dispose();
        const cancelled = make();
        cancelled.handleInput('\\x1b');
        cancelled.handleInput('\\x1b');
        cancelled.showAnswer('late');
        cancelled.dispose();
        console.log(JSON.stringify({{ answer, error, closes, aborted: signals.every((signal) => signal.aborted) }}));
        """
    )
    assert "legacy answer" in result["answer"]
    assert "7 tokens" in result["answer"]
    assert "legacy failure" in result["error"]
    assert result["closes"] == 1
    assert result["aborted"] is True
