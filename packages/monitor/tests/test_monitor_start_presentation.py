from test_monitor_package import run_harness


def test_start_snapshot_is_pending_and_prioritizes_effective_configuration() -> None:
    run_harness(r'''
      try {
        const args={command:"sleep 30",description:"fixture",result_pattern:"DONE"};
        const result=await start.execute("start-config",args,undefined,undefined,ctx());
        assert.equal(result.details.startConfiguration.cwd,process.cwd());
        assert.equal(result.details.startConfiguration.timeoutMs,600000);
        assert.equal(result.details.startConfiguration.completion,"match");
        const colors=[];
        const tint={...theme,fg:(name,text)=>{colors.push(name);return text;},bg:(name,text)=>{colors.push(name);return text;}};
        const component=start.renderResult(result,{expanded:true},tint,{args,isError:false});
        const lines=paint(component,80).join("\n");
        for(const text of ["Command:","Success condition: DONE"]) assert.ok(lines.includes(text),text);
        for(const absent of ["pending at start","terminal ·","Completion:","Timeout:","cwd ·","id ·","command ·"]) assert.ok(!lines.includes(absent),absent);
        assert.ok(lines.indexOf("Command:")<lines.indexOf("Success condition:"));
        assert.ok(colors.includes("warning")); assert.ok(colors.includes("toolPendingBg"));
        assert.ok(!colors.includes("toolSuccessBg"));
        assert.deepEqual(Object.keys(result.structuredContent).sort(),["description","monitorId","status"]);
        assert.ok(!result.content[0].text.includes("cwd="));
        assert.ok(!result.content[0].text.includes("sleep 30"));
        const before=result.content[0].text;
        paint(start.renderResult(result,{expanded:false},theme,{args,isError:false}),40);
        assert.equal(result.content[0].text,before);
      } finally {await shutdown();}
    ''')


def test_restored_start_snapshot_keeps_exact_command_and_native_expansion() -> None:
    run_harness(r'''
      try {
        const args={command:"sleep 30\n#"+"configuration detail ".repeat(30),description:"fixture",result_pattern:"DONE",failure_pattern:"FATAL",completion:"exit",timeout_ms:1234};
        const result=await start.execute("snapshot",args,undefined,undefined,ctx());
        await stop.execute("stop",{});
        const colors=[];
        const tint={...theme,fg:(name,text)=>{colors.push(name);return text;},bg:(name,text)=>{colors.push(name);return text;}};
        const component=start.renderResult(JSON.parse(JSON.stringify(result)),{expanded:true},tint,{args:{},isError:false});
        const text=paint(component,80).join("\n");
        assert.ok(text.includes("Completion: exit (result match + exit 0)"));
        assert.ok(text.includes("Timeout: 1.234s"));
        assert.ok(text.includes("Failure condition: FATAL"));
        assert.ok(text.includes("configuration detail"));
        assert.equal(result.details.startConfiguration.command,args.command);
        assert.ok(!text.includes("terminal ·")&&!/running/i.test(text),"historical start snapshot must not claim current running state");
        const collapsed=paint(start.renderResult(result,{expanded:false},theme,{args,isError:false}),120).join("\n");
        assert.ok(collapsed.includes("[monitor] started · fixture"));
        assert.ok(collapsed.includes("to expand"));
        paint(component,20);
      } finally {await shutdown();}
    ''')


def test_start_configuration_preserves_meaningful_whitespace() -> None:
    run_harness(r'''
      const {mkdtempSync,rmSync}=await import("node:fs");
      const cwd=mkdtempSync("/tmp/monitor  cwd-");
      try {
        const args={command:"sleep 30; printf 'a  b'\n#  indented",description:"spaces",result_pattern:"a  b",failure_pattern:"FATAL  ERROR"};
        const result=await start.execute("spaces",args,undefined,undefined,ctx({cwd}));
        const restored=JSON.parse(JSON.stringify(result));
        const text=paint(start.renderResult(restored,{expanded:true},theme,{args:{},isError:false}),120).join("\n");
        for(const expected of ["printf 'a  b'","#  indented","Success condition: a  b","Failure condition: FATAL  ERROR"]) assert.ok(text.includes(expected),expected);
        assert.ok(!text.includes("cwd ·"),"cwd has no parameter and equals the session cwd");
        const controls={...restored,details:{...restored.details,startConfiguration:{...restored.details.startConfiguration,command:"printf 'a\tb'\r\n#safe"}}};
        const controlText=paint(start.renderResult(controls,{expanded:true},theme,{args:{},isError:false}),80).join("\n");
        assert.ok(controlText.includes("Command (escaped controls):"));
        assert.ok(controlText.includes("a\\tb"));
        assert.ok(!controlText.includes("\t") && !controlText.includes("\r"));
      } finally {await shutdown();rmSync(cwd,{recursive:true,force:true});}
    ''')


def test_start_command_carries_pi_syntax_color() -> None:
    run_harness(r'''
      try {
        const { initTheme } = await import("@earendil-works/pi-coding-agent");
        initTheme("dark");
        const args={command:"set -e\necho DONE",description:"fixture",result_pattern:"DONE"};
        const result=await start.execute("syntax",args,undefined,undefined,ctx());
        const styled=start.renderResult(result,{expanded:true},theme,{args,isError:false}).render(80);
        const command=styled.find((row)=>stripVTControlCharacters(row).trim()==="set -e");
        assert.ok(command!==undefined,"the command keeps its own row");
        assert.ok(command.includes("\u001b["),"the command row carries Pi theme color");
        assert.equal(stripVTControlCharacters(command).trim(),"set -e","the command text survives its color");
        const label=styled.find((row)=>stripVTControlCharacters(row).trim()==="Command:");
        assert.ok(label!==undefined,"the label keeps its own row");
        assert.ok(!label.includes("\u001b["),"the label keeps kit's plain text color");
      } finally {await shutdown();}
    ''')
