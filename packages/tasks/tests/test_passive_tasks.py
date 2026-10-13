"""Confirmed passive contract: tools record state, but do not control model execution."""
from task_helpers import run_node


def test_extension_registers_tools_and_persistence_without_execution_hooks():
    result = run_node('''
      import * as t from "./index.ts";
      const hooks = []; const tools = []; const renderers = [];
      t.default({registerTool(tool){tools.push(tool.name)}, on(name){hooks.push(name)},
        registerMessageRenderer(name){renderers.push(name)}, events:{emit(){}}});
      console.log(JSON.stringify({hooks, tools, renderers}));
    ''')
    assert sorted(result["tools"]) == ["create_task", "get_task", "list_tasks", "update_task"]
    assert result["hooks"] == ["session_start"]
    assert result["renderers"] == []


def test_retired_execution_and_rendering_exports_are_absent():
    result = run_node('''
      import * as t from "./index.ts";
      const retired=["TaskStopCheck","registerTaskStopCheck","taskStatusSpec",
        "TASK_STATUS_MESSAGE_TYPE","TASK_CAPABILITY_NOTE","injectTaskCapabilityNote",
        "createTaskStatusRenderer","MAX_TASK_CONTINUATIONS","MAX_REMINDER_TASKS","MAX_REMINDER_BYTES"];
      console.log(JSON.stringify({remaining:retired.filter(name=>name in t)}));
    ''')
    assert result["remaining"] == []


def test_explicit_list_and_get_preserve_unfinished_work_and_evidence():
    result = run_node('''
      import * as t from "./index.ts";
      t.createTask({id:"open",subject:"Open"});
      t.createTask({id:"blocked",subject:"Blocked",verify:"Read the output"});
      t.blockTask("blocked","main","Access required");
      const list=await t.executeTaskList({statusFilter:["pending","in_progress","blocked"]});
      const detail=await t.executeTaskGet({id:"blocked"});
      console.log(JSON.stringify({list:list.details,detail:detail.details}));
    ''')
    assert {row["id"] for row in result["list"]["tasks"]} == {"open", "blocked"}
    assert result["detail"]["task"]["blockedReason"] == "Access required"
    assert result["detail"]["task"]["verify"] == "Read the output"
