from __future__ import annotations

import json
import re

from test_btw_package import SRC, run_typescript


def test_focus_editing_and_small_layouts() -> None:
    result = run_typescript(f"""
      import {{ createBtwOverlay }} from {json.dumps((SRC / 'overlay.ts').as_uri())};
      import {{ isFocusable, CURSOR_MARKER, visibleWidth }} from '@earendil-works/pi-tui';
      const tui = {{ terminal: {{ rows: 40, columns: 80 }}, requestRender() {{}} }};
      const plainStyle = Object.fromEntries(Object.keys(testStyle).map(key => [key, (text) => text]));
      plainStyle.fg = (_color, text) => text;
      const overlay = createBtwOverlay(tui, plainStyle, {{ question: 'first', onCancel() {{}}, onSpawn() {{}} }});
      overlay.showAnswer('answer');
      const focusable = isFocusable(overlay);
      overlay.focused = false;
      const unfocused = overlay.render(80).join('\n').includes(CURSOR_MARKER);
      overlay.focused = true;
      overlay.handleInput('x'); overlay.handleInput('\x1b[H'); overlay.handleInput('y');
      const composer = overlay.render(80).join('\n');
      const layouts = [];
      for (const rows of [8, 12, 16, 18, 24, 40]) {{
        tui.terminal.rows = rows;
        for (const width of [20, 60, 100]) {{
          tui.terminal.columns = width;
          const lines = overlay.render(width);
          layouts.push({{ rows, width, height: lines.length, fits: lines.every(line => visibleWidth(line) <= width), input: lines.some(line => line.includes(CURSOR_MARKER)) }});
        }}
      }}
      for (const state of ['error', 'loading']) {{
        if (state === 'error') overlay.showError('failure');
        else {{ overlay.handleInput('next'); overlay.handleInput('\\r'); }}
        for (const rows of [8, 12, 16, 24, 40]) {{
          tui.terminal.rows = rows;
          const lines = overlay.render(20);
          layouts.push({{ rows, width: 20, height: lines.length, fits: lines.every(line => visibleWidth(line) <= 20), input: state === 'loading' || lines.some(line => line.includes(CURSOR_MARKER)) }});
        }}
      }}
      overlay.dispose();
      console.log(JSON.stringify({{ focusable, unfocused, composer, layouts }}));
    """.replace("'\n'", "'\\n'").replace("'\x1b[H'", "'\\x1b[H'"))
    assert result['focusable'] is True
    assert result['unfocused'] is False
    plain = re.sub(r'\x1b\[[0-9;]*m|\x1b_pi:c\x07', '', result['composer'])
    assert 'yx' in plain
    for layout in result['layouts']:
        assert layout['height'] <= int(layout['rows'] * 0.8)
        assert layout['fits'] and layout['input']


def test_normalized_wheel_and_loading_invalidation() -> None:
    result = run_typescript(f"""
      import {{ createBtwOverlay }} from {json.dumps((SRC / 'overlay.ts').as_uri())};
      let renders = 0;
      const tui = {{ terminal: {{ rows: 40, columns: 80 }}, requestRender() {{ renders++; }} }};
      const plainStyle = Object.fromEntries(Object.keys(testStyle).map(key => [key, (text) => text]));
      plainStyle.fg = (_color, text) => text;
      const overlay = createBtwOverlay(tui, plainStyle, {{ question: 'first', onCancel() {{}}, onSpawn() {{}} }});
      overlay.invalidate();
      const before = renders;
      await new Promise(resolve => setTimeout(resolve, 250));
      const animated = renders > before;
      overlay.showAnswer(Array.from({{length: 60}}, (_, i) => `line-${{i}}`).join('\n\n'));
      const bottom = overlay.render(80).join('\n');
      const wheel = overlay.handleMouse?.({{ type: 'wheel', wheelDelta: -1000 }});
      const top = overlay.render(80).join('\n');
      overlay.dispose();
      console.log(JSON.stringify({{ animated, bottom, top, handled: wheel?.handled }}));
    """.replace("'\n\n'", "'\\n\\n'").replace("'\n'", "'\\n'"))
    assert result['animated'] is True
    assert result['handled'] is True
    assert 'line-59' in result['bottom']
    assert 'line-0' in result['top']
