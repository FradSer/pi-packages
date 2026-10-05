from __future__ import annotations

import json

import pytest

from test_btw_package import SRC, run_typescript


@pytest.mark.parametrize("max_chars", [0, 1, 12, 4000])
def test_context_character_budget_includes_marker(max_chars: int) -> None:
    result = run_typescript(
        f"""
        import {{ buildConversationContext }} from {json.dumps((SRC / 'context.ts').as_uri())};
        const manager = {{ getBranch: () => [{{ type: 'message', message: {{
          role: 'user', content: 'x'.repeat(5000) + 'tail'
        }} }}] }};
        console.log(JSON.stringify({{ text: buildConversationContext(manager, {{ maxChars: {max_chars} }}) }}));
        """
    )
    assert len(result["text"]) <= max_chars
    if max_chars > 1:
        assert result["text"].endswith("tail")


def test_context_selects_recent_text_in_chronological_order() -> None:
    result = run_typescript(
        f"""
        import {{ buildConversationContext }} from {json.dumps((SRC / 'context.ts').as_uri())};
        const message = (role, content) => ({{ type: 'message', message: {{ role, content }} }});
        const manager = {{ getBranch: () => [
          message('user', 'old'), message('assistant', 'one'),
          message('toolResult', 'ignored'), message('user', 'two'),
          message('assistant', [{{ type: 'thinking', thinking: 'private' }}, {{ type: 'text', text: 'three' }}]),
          message('user', 'four'), message('assistant', '   ')
        ] }};
        console.log(JSON.stringify({{
          text: buildConversationContext(manager),
          disabled: buildConversationContext(manager, {{ maxMessages: 0 }})
        }}));
        """
    )
    assert result == {"text": "[assistant] one\n\n[user] two\n\n[assistant] three\n\n[user] four", "disabled": ""}


def test_jsonl_keeps_last_answer_and_usage() -> None:
    result = run_typescript(
        f"""
        import {{ parseBtwOutput }} from {json.dumps((SRC / 'spawner.ts').as_uri())};
        const event = (content, usage) => JSON.stringify({{
          type: 'message_end', message: {{ role: 'assistant', content, usage }}
        }});
        const stdout = ['not json', event([{{ type: 'text', text: 'old' }}]),
          event([{{ type: 'thinking', text: 'hidden' }}, {{ type: 'text', text: ' final ' }}], {{ totalTokens: 7, cost: {{ total: 0.01 }} }}),
          event([{{ type: 'toolCall', name: 'read' }}])].join('\\n');
        console.log(JSON.stringify(parseBtwOutput(stdout)));
        """
    )
    assert result == {"text": "final", "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 7, "cost": 0.01}}


def test_cancelled_followup_ignores_late_result_and_keeps_input_active() -> None:
    result = run_typescript(
        f"""
        import {{ createBtwOverlay }} from {json.dumps((SRC / 'overlay.ts').as_uri())};
        let closeCount = 0;
        const calls = [];
        const pending = [];
        const overlay = createBtwOverlay({{ terminal: {{ rows: 40, columns: 80 }}, requestRender() {{}} }}, testStyle, {{
          question: 'first', onCancel: () => closeCount++,
          onAsk: (question, history, signal) => {{
            calls.push({{ question, history, signal }});
            return new Promise((resolve) => pending.push(resolve));
          }}
        }});
        const answer = (text) => ({{ text, timedOut: false, exitCode: 0, stderr: '' }});
        pending[0](answer('first answer'));
        await flush();
        overlay.handleInput('cancelled');
        overlay.handleInput('\\r');
        overlay.handleInput('\\x1b');
        overlay.handleInput('replacement');
        overlay.handleInput('\\r');
        pending[1](answer('stale answer'));
        pending[2](answer('replacement answer'));
        await flush();
        const rendered = overlay.render(80).join('\\n');
        overlay.handleInput('\\x1b');
        overlay.handleInput('\\x1b');
        overlay.dispose();
        console.log(JSON.stringify({{
          rendered, closeCount, aborted: calls[1].signal.aborted,
          history: calls[2].history
        }}));
        """
    )
    assert result["aborted"] is True
    assert result["closeCount"] == 1
    assert result["history"] == [{"question": "first", "answer": "first answer"}]
    assert "replacement answer" in result["rendered"]
    assert "stale answer" not in result["rendered"]
    assert "cancelled" not in result["rendered"]
