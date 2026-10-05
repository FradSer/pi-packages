from __future__ import annotations

from test_monitor_package import run_harness


CONSOLE = r'''
let component;
const tui = { terminal: { rows: 24, columns: 80 }, requestRender() {} };
const ui = {
  custom(factory) {
    component = factory(tui, theme, {}, () => {});
    return Promise.resolve();
  },
  notify() {}, setWidget() {},
};
const open = () => commands.get("monitor").handler("", ctx({ ui }));
const frame = () => {
  const rows = paint(component, tui.terminal.columns);
  assert.ok(rows.length <= tui.terminal.rows, `${rows.length} lines exceed ${tui.terminal.rows} rows`);
  assert.ok(!component.render(tui.terminal.columns).join("").includes("\u009b"));
  return rows.join("\n");
};
'''


def test_console_diagnostics_disclosure_scroll_and_resize() -> None:
    run_harness(CONSOLE + r'''
      try {
        await start.execute("diagnostics", {
          command: `node -e "for(let i=0;i<80;i++) console.log('diagnostic-' + i); process.exit(1)"`,
          description: "diagnostic fixture",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
        await open();
        assert.ok(!frame().includes("diagnostic-79"), "terminal.output is hidden by default");
        component.handleInput("\r");
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("diagnostic-79"), "End exposes the final output line");
        component.handleInput("\u001b[H");
        assert.ok(frame().includes("Status: failure"), "Home returns to the first detail row");
        for (const rows of [12, 7, 6, 5, 3, 1, 24]) {
          tui.terminal.rows = rows;
          tui.terminal.columns = rows === 1 ? 8 : 40;
          frame();
          component.handleInput("\u001b[F");
          frame();
        }
        tui.terminal.rows = 1; tui.terminal.columns = 80;
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("diagnostic-79"), "one-row terminals can reach output");
        tui.terminal.rows = 24; tui.terminal.columns = 80;
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("diagnostic-79"));
        component.handleInput("\r");
        assert.ok(!frame().includes("diagnostic-79"), "hiding output resets its scroll position");
      } finally { await shutdown(); }
    ''')


def test_console_selection_follows_monitor_id_after_completion() -> None:
    run_harness(CONSOLE + r'''
      try {
        const first = await start.execute("first", { command: "sleep 10", description: "first fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        await start.execute("second", { command: "sleep 10", description: "second fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        await open();
        assert.ok(frame().includes("(running) first fixture"));
        await stop.execute("finish-first", { monitor_id: first.details.monitorId });
        assert.ok(frame().includes("(stopped) first fixture"), "completion must not select another monitor at the same index");
        component.handleInput("x");
        assert.ok(frame().includes("(running) second fixture"), "x on finished selection must not stop a different monitor");
      } finally { await shutdown(); }
    ''')


def test_console_list_viewport_and_independent_detail_navigation() -> None:
    run_harness(CONSOLE + r'''
      try {
        for (let i = 0; i < 10; i++) {
          await start.execute(`task-${i}`, {
            command: "sleep 10", description: `fixture-${i}\u001b[31m\u009b32m`, result_pattern: "NEVER",
          }, undefined, undefined, ctx());
        }
        await open();
        tui.terminal.rows = 12;
        for (let i = 0; i < 9; i++) component.handleInput("\u001b[B");
        assert.ok(frame().includes("(running) fixture-9"));
        component.handleInput("\u001b[6~");
        frame();
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("Logs: 0 retained"), "last detail is reachable");
        component.handleInput("\u001b[5~");
        frame();
        component.handleInput("\u001b[H");
        assert.ok(frame().includes("Status: running"), "Home returns to the first detail row");
      } finally { await shutdown(); }
    ''')


def test_fullscreen_host_routes_scroll_keys_to_console() -> None:
    run_harness(r'''
      import { TuiAltScreen, TUI_KEYBINDINGS } from "@earendil-works/pi-tui";
      setKeybindings(new KeybindingsManager(TUI_KEYBINDINGS));
      let input;
      let component;
      const terminal = new Proxy({
        rows: 24, columns: 80, kittyProtocolActive: false,
        start(onInput) { input = onInput; },
      }, { get(target, name) { return target[name] ?? (() => {}); } });
      const tui = new TuiAltScreen(terminal, false, undefined, { mouse: false });
      const received = [];
      const ui = {
        custom(factory, options) {
          let overlay;
          component = factory(tui, theme, {}, () => overlay?.hide());
          const handler = component.handleInput;
          component.handleInput = (data) => { received.push(data); handler(data); };
          if (options?.overlay) overlay = tui.showOverlay(component, options.overlayOptions);
          else { tui.addChild(component); tui.setFocus(component); }
          return Promise.resolve();
        }, notify() {}, setWidget() {},
      };
      try {
        await start.execute("fullscreen", {
          command: `node -e "for(let i=0;i<80;i++) console.log('diagnostic-' + i); process.exit(1)"`,
          description: "fullscreen fixture", result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx({ mode: "print", hasUI: false }));
        await commands.get("monitor").handler("", ctx({ ui }));
        tui.start();
        paint(component, 80);
        input("\r");
        for (const key of ["\u001b[6~", "\u001b[F", "\u001b[5~", "\u001b[H"]) input(key);
        assert.deepEqual(received, ["\r", "\u001b[6~", "\u001b[F", "\u001b[5~", "\u001b[H"],
          "fullscreen viewport must defer paging and Home/End to the console");
        input("\u001b[F");
        assert.ok(paint(component, 80).join("\n").includes("diagnostic-79"));
        input("q");
      } finally { tui.stop(); await shutdown(); }
    ''')


def test_console_long_names_keep_status_and_narrow_help_is_reachable() -> None:
    run_harness(CONSOLE + r'''
      try {
        await start.execute("long-name", {
          command: "sleep 10", description: "发布验证中文long-description-".repeat(12), result_pattern: "NEVER",
        }, undefined, undefined, ctx());
        await open();
        for (const columns of [80, 40, 20]) {
          tui.terminal.columns = columns;
          const rows = paint(component, columns);
          assert.ok(rows[2].includes("running"), `state must survive long descriptions: ${rows.join("\n")}`);
          assert.ok(rows.at(-2).includes("? help"), `help must remain discoverable: ${rows.join("\n")}`);
        }
        tui.terminal.rows = 6; tui.terminal.columns = 20;
        assert.ok(paint(component, 20).at(-1).includes("? help"));
        component.handleInput("?");
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("stop all"), "all shortcuts are reachable even at 20x6");
        component.handleInput("?");
        assert.ok(frame().includes("running"), "help restores selection and details");
      } finally { await shutdown(); }
    ''')


def test_console_refresh_timer_is_scoped_and_cleared_on_close() -> None:
    run_harness(CONSOLE + r'''
      const originalSet = globalThis.setInterval;
      const originalClear = globalThis.clearInterval;
      let tick, cleared = false, renders = 0;
      const timer = { unref() {} };
      try {
        await start.execute("live", { command: "sleep 10", description: "live fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        globalThis.setInterval = (callback, ms) => {
          assert.ok(ms >= 200, "refresh must be bounded"); tick = callback; return timer;
        };
        globalThis.clearInterval = (value) => { if (value === timer) cleared = true; else originalClear(value); };
        tui.requestRender = () => { renders++; };
        ui.custom = (factory) => new Promise((resolve) => { component = factory(tui, theme, {}, resolve); });
        const opening = open();
        assert.equal(typeof tick, "function", "open console must refresh live output");
        const before = renders;
        tick();
        assert.ok(renders > before);
        assert.equal(sent.length, 0, "refresh never emits model messages");
        component.handleInput("q");
        await opening;
        assert.ok(cleared, "closing console clears its refresh timer");
      } finally {
        globalThis.setInterval = originalSet; globalThis.clearInterval = originalClear;
        await shutdown();
      }
    ''')


def test_open_console_repaints_new_output_before_terminal_result() -> None:
    run_harness(CONSOLE + r'''
      let renders = 0;
      tui.requestRender = () => { renders++; };
      ui.custom = (factory) => new Promise((resolve) => { component = factory(tui, theme, {}, resolve); });
      try {
        await start.execute("progress", {
          command: `node -e "let i=0; setInterval(()=>console.log('live-'+(++i)),100)"`,
          description: "live output", result_pattern: "NEVER",
        }, undefined, undefined, ctx());
        const opening = open();
        component.handleInput("\r");
        const before = renders;
        await new Promise((resolve) => setTimeout(resolve, 600));
        assert.ok(renders >= before + 2, "live progress requests fresh frames while idle");
        component.handleInput("\u001b[F");
        assert.ok(frame().includes("live-"), "new output is visible before completion");
        assert.ok(frame().includes("running"));
        assert.equal(sent.length, 0);
        component.handleInput("q");
        await opening;
        const closedRenders = renders;
        await new Promise((resolve) => setTimeout(resolve, 300));
        assert.equal(renders, closedRenders, "closed console has no background repaints");
      } finally { await shutdown(); }
    ''')


def test_console_shortcuts_decode_kitty_and_ignore_releases_or_control_keys() -> None:
    run_harness(CONSOLE + r'''
      let closed = 0;
      ui.custom = (factory) => { component = factory(tui, theme, {}, () => { closed++; }); return Promise.resolve(); };
      try {
        await start.execute("kitty", { command: "sleep 10", description: "kitty fixture", result_pattern: "NEVER" }, undefined, undefined, ctx());
        await open();
        for (const key of ["\u001b[63u", "\u001b[47:63;2u", "\u001b[27;2;63~", "\u001b[27;1;63~"]) {
          component.handleInput(key);
          assert.ok(frame().includes("Monitor controls"), "encoded question mark opens help");
          component.handleInput("?");
        }
        component.handleInput("\u001b[120;1:3u");
        component.handleInput("\u001b[120;5u");
        component.handleInput("\u001b[27;5;120~");
        component.handleInput("\u001b[27;3;120~");
        component.handleInput("\u001b[27;5;113~");
        assert.equal(closed, 0);
        assert.ok(frame().includes("running"), "release and Ctrl+x must not stop work");
        component.handleInput("\u001b[120u");
        assert.ok(frame().includes("stopped"), "Kitty x stops selected work");
        component.handleInput("\u001b[27;1;113~");
        assert.equal(closed, 1, "modifyOtherKeys q closes console");
        await open();
        component.handleInput("\u001b[113u");
        assert.equal(closed, 2, "Kitty q closes console");
      } finally { await shutdown(); }
    ''')
