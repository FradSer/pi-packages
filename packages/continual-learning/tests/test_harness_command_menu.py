from __future__ import annotations

import json
from pathlib import Path

from support import isolated_run_bun as run_bun


def test_harness_menu_lists_rule_and_shows_bounded_details(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks = {{}}, commands = {{}}, notices = [], selections = [];
      register({{
        on: (n, f) => hooks[n] = f,
        registerCommand: (n, c) => commands[n] = c,
        registerEntryRenderer() {{}}, appendEntry() {{}},
        getCommands: () => [], sendUserMessage() {{}}
      }});
      const cwd = {json.dumps(str(tmp_path))};
      fs.mkdirSync(path.join(cwd, '.pi'), {{recursive: true}});
      fs.writeFileSync(path.join(cwd, '.pi/harness.json'), JSON.stringify({{rules:[{{
            id:'long-guidance', text:'secret', instructions:'Full guidance that must be visible in the rule details.'
      }}]}}));
      const ui = {{
        notify: (message, type) => notices.push({{message, type}}),
        select: async (title, options) => {{
          selections.push({{title, options}});
          if (selections.filter(item => item.title === title).length > 1) return undefined;
          if (title === 'Harness rules') return options[0];
          return 'Close';
        }},
        input: async () => undefined,
      }};
      await commands.harness.handler('', {{cwd, hasUI:true, ui}});
      console.log(JSON.stringify({{notices, selections}}));
    ''')
    assert result["selections"][0]["title"] == "Harness rules"
    assert any("long-guidance" in option for option in result["selections"][0]["options"])
    assert "Create or update rule" in result["selections"][0]["options"]
    assert not any("diagnostic" in option.lower() for option in result["selections"][0]["options"])
    assert any("Full guidance that must be visible" in item["title"] for item in result["selections"])
    assert any(".pi/harness.json" in item["title"] for item in result["selections"])


def test_harness_menu_cancel_does_not_send_a_follow_up(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}, sent = [], selections = [];
      register({{
        on() {{}}, registerCommand: (n, c) => commands[n] = c,
        registerEntryRenderer() {{}}, appendEntry() {{}}, getCommands: () => [],
        sendUserMessage: (...args) => sent.push(args)
      }});
      const cwd = {json.dumps(str(tmp_path))};
      fs.mkdirSync(path.join(cwd, '.pi'), {{recursive: true}});
      const ui = {{
        notify() {{}},
        select: async (title, options) => {{
          selections.push({{title, options}});
          if (selections.filter(item => item.title === title).length > 1) return undefined;
          if (title === 'Harness rules') return 'Create or update rule';
          return 'Cancel';
        }},
        input: async () => 'must never be sent',
      }};
      await commands.harness.handler('', {{cwd, hasUI:true, ui}});
      console.log(JSON.stringify({{sent, selections}}));
    ''')
    assert result["sent"] == []
    scope_selection = next(item for item in result["selections"] if item["title"] == "Where should this rule live?")
    assert scope_selection["options"][:3] == [
        "Project shared (default)",
        "Project personal",
        "Global shared",
    ]


def test_harness_menu_is_not_used_without_ui(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}, notices = [];
      register({{on() {{}}, registerCommand: (n, c) => commands[n] = c,
        registerEntryRenderer() {{}}, appendEntry() {{}}, getCommands: () => []}});
      await commands.harness.handler('', {{cwd:{json.dumps(str(tmp_path))}, hasUI:false,
        ui:{{notify: (message) => notices.push(message)}}}});
      console.log(JSON.stringify(notices));
    ''')
    assert any("config paths:" in message for message in result)
    assert any("project-scoped personal" in message for message in result)


def test_harness_menu_exposes_bounded_diagnostics_for_invalid_config(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}, notices = [], selections = [];
      register({{on() {{}}, registerCommand: (n, c) => commands[n] = c,
        registerEntryRenderer() {{}}, appendEntry() {{}}, getCommands: () => []}});
      const cwd = {json.dumps(str(tmp_path))};
      fs.mkdirSync(path.join(cwd, '.pi'), {{recursive: true}});
      fs.writeFileSync(path.join(cwd, '.pi/harness.json'), JSON.stringify({{rules: 'broken'}}));
      const ui = {{
        notify: (message, type) => notices.push({{message, type}}),
        select: async (title, options) => {{
          selections.push({{title, options}});
          if (selections.filter(item => item.title === title).length > 1) return undefined;
          return options.find(option => option.toLowerCase().includes('diagnostic')) ?? 'Close';
        }},
        input: async () => undefined,
      }};
      await commands.harness.handler('', {{cwd, hasUI:true, ui}});
      console.log(JSON.stringify({{notices, selections}}));
    ''')
    assert any("diagnostic" in option.lower() for option in result["selections"][0]["options"])
    assert any("errors:" in item["title"].lower() or "harness config" in item["title"].lower() for item in result["selections"])


def test_harness_menu_pages_all_rules_and_keeps_page_count(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}, notices = [], selections = [], rules = [];
      for (let i = 1; i <= 41; i++) rules.push({{id:`rule-${{i}}`, text:`subject-${{i}}`, instructions:`guidance-${{i}}`}});
      register({{on() {{}}, registerCommand: (n, c) => commands[n] = c,
        registerEntryRenderer() {{}}, appendEntry() {{}}, getCommands: () => []}});
      const cwd = {json.dumps(str(tmp_path))};
      fs.mkdirSync(path.join(cwd, '.pi'), {{recursive: true}});
      fs.writeFileSync(path.join(cwd, '.pi/harness.json'), JSON.stringify({{rules}}));
      const ui = {{
        notify: (message, type) => notices.push({{message, type}}),
        select: async (title, options) => {{
          selections.push({{title, options}});
          if (selections.filter(item => item.title === title).length > 1) return undefined;
          if (title.startsWith('Harness rules')) {{
            const rule = options.find(option => option.includes('rule-41'));
            if (rule) return rule;
            return options.find(option => option.toLowerCase().startsWith('next page')) ?? 'Close';
          }}
          return 'Close';
        }},
        input: async () => undefined,
      }};
      await commands.harness.handler('', {{cwd, hasUI:true, ui}});
      console.log(JSON.stringify({{notices, selections}}));
    ''')
    menus = [item for item in result["selections"] if item["title"].startswith("Harness rules")]
    assert len(menus) >= 2, menus
    assert all("/" in item["title"] for item in menus), menus
    assert any("rule-41" in option for option in menus[-1]["options"]), menus[-1]
    assert any("guidance-41" in item["title"] for item in result["selections"])


def test_harness_menu_long_ids_have_unique_selectable_labels(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}, notices = [], selections = [];
      const prefix = 'long-rule-' + 'x'.repeat(150);
      register({{on() {{}}, registerCommand: (n, c) => commands[n] = c,
        registerEntryRenderer() {{}}, appendEntry() {{}}, getCommands: () => []}});
      const cwd = {json.dumps(str(tmp_path))};
      fs.mkdirSync(path.join(cwd, '.pi'), {{recursive: true}});
      fs.writeFileSync(path.join(cwd, '.pi/harness.json'), JSON.stringify({{rules:[
        {{id:prefix+'-one', text:'same', instructions:'first guidance'}},
        {{id:prefix+'-two', text:'same', instructions:'second guidance'}}
      ]}}));
      const ui = {{
        notify: (message, type) => notices.push({{message, type}}),
        select: async (title, options) => {{
          selections.push({{title, options}});
          if (selections.filter(item => item.title === title).length > 1) return undefined;
          if (title === 'Harness rules') {{
            const rules = options.filter(option => !['Create or update rule', 'Close'].includes(option));
            const colliding = rules.filter(option => option.includes(' · #'));
            if (colliding.length >= 2) return colliding[1];
          }}
          return 'Close';
        }},
        input: async () => undefined,
      }};
      await commands.harness.handler('', {{cwd, hasUI:true, ui}});
      console.log(JSON.stringify({{notices, selections}}));
    ''')
    rule_options = [option for option in result["selections"][0]["options"] if option not in ["Create or update rule", "Close"]]
    assert len(rule_options) == len(set(rule_options)), rule_options
    assert any("second guidance" in item["title"] for item in result["selections"])


def test_harness_menu_empty_request_uses_empty_default_and_does_not_send(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}, sent = [], inputs = [];
      register({{on() {{}}, registerCommand: (n, c) => commands[n] = c,
        registerEntryRenderer() {{}}, appendEntry() {{}}, getCommands: () => [],
        sendUserMessage: (...args) => sent.push(args)}});
      const ui = {{
        notify() {{}},
        select: async (title, options) => title === 'Harness rules' ? 'Create or update rule' : 'Project shared (default)',
        input: async (title, defaultValue) => {{ inputs.push([title, defaultValue]); return ''; }},
      }};
      await commands.harness.handler('', {{cwd:{json.dumps(str(tmp_path))}, hasUI:true, ui}});
      console.log(JSON.stringify({{sent, inputs}}));
    ''')
    assert result["sent"] == []
    assert result["inputs"] == [["Create or update a Harness rule", ""]]


def test_scoped_user_menu_shows_the_actual_config_file(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const {{configPaths}} = await import('./packages/continual-learning/extensions/guardrail-config.ts');
      const commands = {{}}, notices = [];
      register({{on(){{}},registerCommand:(name,command)=>commands[name]=command,registerEntryRenderer(){{}},getCommands:()=>[]}});
      const cwd={json.dumps(str(tmp_path))}, paths=configPaths(cwd);
      const {{assertProjectScopeOwner}} = await import('./packages/continual-learning/extensions/memory-paths.ts');
      assertProjectScopeOwner(cwd);
      fs.mkdirSync(path.dirname(paths.userScoped),{{recursive:true}});
      fs.writeFileSync(paths.userScoped,JSON.stringify({{rules:[{{id:'scoped-view',text:'needle',instructions:'Scoped guidance'}}]}}));
      await commands.harness.handler('',{{cwd,hasUI:true,ui:{{
        select:async(title,options)=>{{notices.push(title);return title==='Harness rules'&&notices.filter(t=>t==='Harness rules').length===1?options.find(option=>option.includes('scoped-view')):undefined;}},
        notify:message=>notices.push(message),input:async()=>undefined,
      }}}});
      console.log(JSON.stringify({{notices,file:paths.userScoped}}));
    ''')
    assert any(result["file"] in notice for notice in result["notices"]), result


def test_scoped_user_source_points_to_scoped_file_in_guardrails_and_guidance(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:registerGuardrails}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const {{default:registerGuidance}} = await import('./packages/continual-learning/extensions/harness-guidance.ts');
      const {{configPaths}} = await import('./packages/continual-learning/extensions/guardrail-config.ts');
      const hooks = {{}}, entries = [], commands = {{}};
      const pi = {{
        on: (name, handler) => hooks[name] = [...(hooks[name] ?? []), handler],
        registerCommand: (name, command) => commands[name] = command,
        registerEntryRenderer() {{}}, appendEntry: (type, data) => entries.push({{type, data}}),
        getCommands: () => [{{name:'skill:known', source:'skill'}}],
      }};
      registerGuardrails(pi); registerGuidance(pi);
      const cwd = {json.dumps(str(tmp_path))};
      const paths = configPaths(cwd);
      const {{assertProjectScopeOwner}} = await import('./packages/continual-learning/extensions/memory-paths.ts');
      assertProjectScopeOwner(cwd);
      fs.mkdirSync(path.dirname(paths.userScoped), {{recursive:true}});
      fs.writeFileSync(paths.userScoped, JSON.stringify({{rules:[
        {{id:'scoped-block', bash:'^fixture$', action:'block', message:'Scoped block'}},
      ], skillPrompts:{{known:{{target:'user',prompt:'Scoped guidance'}}}}}}));
      const blocked = await hooks.tool_call[0]({{toolName:'bash',toolCallId:'fixture',input:{{command:'fixture'}}}}, {{cwd,hasUI:false}});
      for (const handler of hooks.before_agent_start ?? []) await handler(
        {{prompt:'<skill name="known" location="/tmp/SKILL.md">\\nbody\\n</skill>\\n\\nneedle',systemPrompt:'base',systemPromptOptions:{{sections:{{}},skills:[{{name:'known'}}]}}}},
        {{cwd,sessionManager:{{buildContextEntries:() => []}}}}
      );
      console.log(JSON.stringify({{blocked,paths,entries}}));
    ''')
    scoped_path = result["paths"]["userScoped"]
    assert result["blocked"]["block"]
    matching = [entry for entry in result["entries"] if entry["data"].get("file") == scoped_path]
    assert any(entry["type"] == "harness-event" for entry in matching), result
    assert any(entry["type"] == "harness-guidance-event" for entry in matching), result


def test_incomplete_bash_event_does_not_claim_builtin_provenance(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / "agent"))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{default:register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}}, entries=[];
      register({{
        on:(name,handler)=>hooks[name]=[...(hooks[name]??[]),handler],
        registerCommand(){{}},
        registerEntryRenderer(){{}},
        appendEntry:(type,data)=>entries.push({{type,data}}),
        getCommands:()=>[],
      }});
      const cwd={json.dumps(str(tmp_path))};
      fs.mkdirSync(path.join(cwd,'.pi'),{{recursive:true}});
      fs.writeFileSync(path.join(cwd,'.pi','harness.json'),JSON.stringify({{rules:[{{id:'invalid-bash',bash:'(',message:'invalid'}}]}}));
      const decision=await hooks.tool_call[0]({{toolName:'bash',toolCallId:'bad',input:{{command:'echo safe'}}}},{{cwd,hasUI:false}});
      console.log(JSON.stringify({{decision,incomplete:entries.find(entry=>entry.data?.policy==='invalid-bash')?.data}}));
    ''')
    assert result['decision']['block'] is True
    assert result['incomplete']['source'] == 'unknown'
    assert result['incomplete']['file'] == '(unknown)'
