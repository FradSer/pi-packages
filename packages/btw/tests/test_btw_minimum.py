from __future__ import annotations

import json

from test_btw_package import SRC, run_typescript


def test_minimum_loading_and_keyboard_reach_last_answer_line() -> None:
    result = run_typescript(f"""
      import {{ createBtwOverlay }} from {json.dumps((SRC / 'overlay.ts').as_uri())};
      const style = Object.fromEntries(Object.keys(testStyle).map(key => [key, text => text]));
      style.fg = (_color, text) => text;
      const overlay = createBtwOverlay({{terminal: {{rows: 8, columns: 20}}, requestRender() {{}}}}, style, {{
        question: 'first', modelLabel: 'anthropic/claude-sonnet-4-6', onCancel() {{}}, onSpawn() {{}}
      }});
      const loading = overlay.render(20);
      overlay.showAnswer(Array.from({{length: 60}}, (_, i) => `line-${{i}}`).join('\n\n'));
      for (let i = 0; i < 200; i++) {{ overlay.handleInput('\x1b[5~'); overlay.render(20); }}
      for (let i = 0; i < 200; i++) {{ overlay.handleInput('\x1b[6~'); overlay.render(20); }}
      const bottom = overlay.render(20).join('\n');
      overlay.dispose();
      console.log(JSON.stringify({{loading, bottom}}));
    """.replace("'\n\n'", "'\\n\\n'").replace("'\n'", "'\\n'"))
    assert len(result['loading']) <= 6
    assert any('esc cancel' in line for line in result['loading'])
    assert 'line-59' in result['bottom']
