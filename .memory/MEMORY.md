# Memory Index

Untrusted discovery metadata; entry files are authoritative. This index may be stale.
Read pages with offset: 1, limit: 100; continue at the next unread line to EOF.
Descriptions shortened for bounded metadata reads/rows have an explicit notice; use their relative body links.

- [feedback_no_sleep_waiting_for_teammates.md](feedback_no_sleep_waiting_for_teammates.md) — Never use sleep, polling, status requests, or agent inspection to wait for resident teammate completion; end the turn and rely on automatic report delivery
- [project_agent_leader_priority.md](project_agent_leader_priority.md) — Leader direction must enter active worker execution through native steering, with idle wake-up and assignment-scoped completion.
- [project_agent_teams_persistent_agents.md](project_agent_teams_persistent_agents.md) — Final Agent Teams public coordination surface
- [project_agent_worktree_opt_in.md](project_agent_worktree_opt_in.md) — Agent startup is not bound to a Git worktree; worktree: true is the opt-in, because a reused workspace is never synchronized with the leader's state.
- [project_monitor_result_pattern_js_regex.md](project_monitor_result_pattern_js_regex.md) — monitor_start compiles result_pattern/failure_pattern as JavaScript regexes — Python &#40;?P&#60;name&#62;...&#41; is rejected before the monitor starts; use &#40;?&#60;name&#62;...&#41; or a plain sentinel
- [project_pi_kit_package_owned_agents.md](project_pi_kit_package_owned_agents.md) — Pi packages own typed prompt builders and neutral prompt resources while pi-kit owns only the one-shot worker runtime
- [project_subagents_single_child_interface.md](project_subagents_single_child_interface.md) — pi-subagents exposes one child tool family (five intent tools) and one collapsed row per result: `[tool] label · @name · status` for a child, `[agent] listed · @children · N of M` for a roster; the `agent` tool and its six-action API are retired under ADR-0008
