from test_monitor_package import run_harness
from test_monitor_console_viewport import CONSOLE


def test_terminal_rows_keep_status_and_use_outcome_colors() -> None:
    run_harness(r'''
      try {
        for (const status of ["success", "failure", "timeout", "result_missing", "stopped"]) {
          const colors = [];
          const tint = { ...theme, fg: (name, text) => { colors.push(name); return text; }, bg: (name, text) => { colors.push(name); return text; } };
          const result = { content: [{type:"text",text:"report"}], details: { description:"业务校验".repeat(30), monitorId:"fixture", result:{status,elapsedMs:1,reason:"fixture"} } };
          for (const custom of [false,true]) {
            colors.length = 0;
            const component = custom
              ? renderers.get("monitor-result")({customType:"monitor-result",...result},{expanded:false},tint)
              : start.renderResult(result,{expanded:false},tint,{args:{},isError:false});
            for (const width of [20,40,80]) assert.ok(paint(component,width).join("\n").includes(status), `${status} lost at ${width}`);
            if (["failure","timeout","result_missing"].includes(status)) {
              assert.ok(colors.includes("error")); assert.ok(colors.includes("toolErrorBg"));
              assert.ok(!colors.includes("toolSuccessBg"));
            } else if (status === "stopped") assert.ok(colors.includes("dim"));
          }
        }
      } finally { await shutdown(); }
    ''')


def test_large_values_preview_and_full_console_disclosure() -> None:
    run_harness(CONSOLE + r'''
      try {
        const value = "a".repeat(24000) + "PAYLOAD_END";
        const args = { command: `node -e 'console.log("DONE " + JSON.stringify({body:"a".repeat(24000)+String.fromCharCode(80,65,89,76,79,65,68,95,69,78,68),ok:true}))'`, description:"large", result_pattern:"DONE (?<json>.*)", completion:"exit" };
        const result = await start.execute("large",args,undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.equal(result.details.result.result.body,value);
        const rows = paint(start.renderResult(result,{expanded:true},theme,{args,isError:false}),80);
        assert.ok(rows.length < 30); assert.ok(rows.join("\n").includes("preview"));
        const unicode = {...result,details:{...result.details,result:{...result.details.result,result:{body:String.fromCodePoint(0x20000).repeat(100)}}}};
        assert.ok(!paint(start.renderResult(unicode,{expanded:true},theme,{args,isError:false}),80).join("\n").includes("preview"), "preview threshold counts Unicode code points");
        await open();
        component.handleInput("\u001b[F");
        assert.ok(!frame().includes("PAYLOAD_END"));
        component.handleInput("v"); component.handleInput("\u001b[F");
        assert.ok(frame().includes("PAYLOAD_END"));
        component.handleInput("v"); component.handleInput("\u001b[F");
        assert.ok(!frame().includes("PAYLOAD_END"));
      } finally {await shutdown();}
    ''')


def test_failure_details_precede_long_command() -> None:
    run_harness(CONSOLE + r'''
      try {
        await start.execute("failure", {command:"exit 2\n#"+"long command ".repeat(300), description:"fixture",result_pattern:"DONE",completion:"exit"},undefined,undefined,ctx({mode:"print",hasUI:false}));
        await open(); tui.terminal.rows=6; tui.terminal.columns=40;
        assert.ok(frame().includes("Exit code: 2"));
        assert.ok(frame().includes("Reason: process_exit"));
      } finally {await shutdown();}
    ''')


def test_parallel_widget_has_adaptive_budget() -> None:
    run_harness(r'''
      let widget;
      const tui={terminal:{rows:24},requestRender(){}};
      const ui={setWidget(_key,factory){widget=factory?.(tui,theme);},notify(){}};
      try {
        await fire("session_start",{},ctx({ui}));
        for(let i=0;i<12;i++) await start.execute(`job-${i}`,{command:"sleep 30",description:`job-${i}`,result_pattern:"DONE"},undefined,undefined,ctx({ui}));
        assert.ok(paint(widget,80).length<=3);
        assert.ok(paint(widget,80).join("\n").includes("10 more"));
        tui.terminal.rows=6;
        assert.equal(paint(widget,40).length,1);
        assert.ok(paint(widget,40).join("\n").includes("12 running"));
      } finally {await shutdown();}
    ''')


def test_restored_and_evicted_results_keep_full_transcript_values() -> None:
    run_harness(r'''
      try {
        const value = "a".repeat(500) + "RESTORED_PAYLOAD_END";
        const restored = {customType:"monitor-result",content:"report",details:{description:"restored",monitorId:"missing",result:{status:"success",elapsedMs:1,result:{body:value}}}};
        const restoredRows = paint(renderers.get("monitor-result")(restored,{expanded:true},theme),80).join("\n").replace(/\s/g, "");
        assert.ok(restoredRows.includes("RESTORED_PAYLOAD_END"));
        const args = {command:`node -e 'console.log("DONE " + JSON.stringify({body:"a".repeat(500)+String.fromCharCode(80,65,89,76,79,65,68,95,69,78,68)}))'`,description:"old",result_pattern:"DONE (?<json>.*)",completion:"exit"};
        const result = await start.execute("old",args,undefined,undefined,ctx({mode:"print",hasUI:false}));
        const tool = start.renderResult(result,{expanded:true},theme,{args,isError:false});
        const custom = renderers.get("monitor-result")({customType:"monitor-result",...result},{expanded:true},theme);
        assert.ok(paint(tool,80).join("\n").includes("preview"));
        for(let i=0;i<20;i++) await start.execute(`new-${i}`,{command:"printf DONE",result_pattern:"DONE"},undefined,undefined,ctx({mode:"print",hasUI:false}));
        for(const component of [tool,custom]) {
          const text = paint(component,80).join("\n").replace(/\s/g, "");
          assert.ok(text.includes("PAYLOAD_END"),"existing components must reveal values after history eviction");
        }
      } finally {await shutdown();}
    ''')


def test_stopped_rows_accept_native_theme_instances() -> None:
    run_harness(r'''
      const { getThemeByName } = await import("./node_modules/@earendil-works/pi-coding-agent/dist/modes/interactive/theme/theme.js");
      const nativeTheme = getThemeByName("dark");
      try {
        const result={content:[{type:"text",text:"report"}],details:{description:"stopped",monitorId:"fixture",result:{status:"stopped",elapsedMs:1}}};
        const component=start.renderResult(result,{expanded:true},nativeTheme,{args:{},isError:false});
        assert.ok(paint(component,80).join("\n").includes("stopped"));
      } finally {await shutdown();}
    ''')
