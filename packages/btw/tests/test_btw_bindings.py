from __future__ import annotations

import json

from test_btw_package import SRC, run_typescript


def test_configured_cancel_works_while_loading_and_idle() -> None:
    result = run_typescript(f"""
      import {{ createBtwOverlay }} from {json.dumps((SRC / 'overlay.ts').as_uri())};
      import {{ KeybindingsManager, setKeybindings, TUI_KEYBINDINGS }} from {json.dumps((SRC.parent / 'node_modules/@earendil-works/pi-tui/dist/index.js').as_uri())};
      setKeybindings(new KeybindingsManager(TUI_KEYBINDINGS, {{ 'tui.select.cancel': 'ctrl+x' }}));
      const states = [];
      for (const answered of [false, true]) {{
        let closes = 0;
        let signal;
        const overlay = createBtwOverlay({{ terminal: {{rows: 40, columns: 80}}, requestRender() {{}} }}, testStyle, {{
          question: 'first', keybindings: new KeybindingsManager(TUI_KEYBINDINGS, {{ 'tui.select.cancel': 'ctrl+x' }}),
          onCancel: () => closes++, onSpawn: value => signal = value
        }});
        if (answered) overlay.showAnswer('answer');
        overlay.handleInput('\u0018');
        states.push({{closes, aborted: signal.aborted}});
        overlay.dispose();
      }}
      console.log(JSON.stringify({{states}}));
    """)
    assert result['states'] == [{'closes': 1, 'aborted': True}, {'closes': 1, 'aborted': True}]
