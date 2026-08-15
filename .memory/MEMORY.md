# Memory Index

## git-agent commit workflow
- `feedback_git_agent_commit_scope.md` — git-agent commit auto-stages the whole dirty tree; scope it with exact staging plus `--no-stage`
- `project_git_agent_session_context.md` — git-agent CLI is conversation-blind; session_context bridges the session record into commit intents

## pi extension & TUI mechanics
- `feedback_no_global_input_interception.md` — extensions must not drive widgets with `onTerminalInput` (breaks pi's model selector/history); own input via `ctx.ui.custom`
- `reference_pi_kitty_csi_u_keys.md` — pi negotiates the Kitty keyboard protocol: Esc is `\x1b[27u`, Shift+arrows are `\x1b[1;2:1A/B`; match with CSI-u-aware regexes
- `reference_pi_custom_component_rendering.md` — `ctx.ui.custom` `render(width)` must wrap/truncate to terminal width; non-overlay custom = full screen
- `reference_pi_cli_print_json_usage.md` — `pi --print --mode json` emits JSONL with `message.usage` (tokens/cost) for child-process cost accounting

## menu commands & interaction UX
- `project_git_github_menu_conversion.md` — settled: workflows are pi menu commands with inline procedures, not skills; manual selection, no autocomplete; git/github menus removed (now skills repo), git-agent menu lives in git-agent/pi-git-agent
- `feedback_memory_menu_inline_consolidation.md` — /memory menu design — consolidate first, single project-instructions entry, consolidation runs in a background child process, auto-triggered at 40% context fill
- `feedback_no_custom_interaction_tools.md` — no custom dialog/confirmation tools (gh_confirm, gh_ask_merge, git_ask_name); ask in the conversation; permission gates are `tool_call` hooks offering options

## npm publishing
- `feedback_pi_package_npm_naming.md` — npm naming ladder: unscoped first, `@fradser` fallback, org scope only with a paid npm org
- `project_pi_package_npm_publishing.md` — Changesets-driven OIDC trusted publishing with a release.yml whitelist; first release needs manual publish + `npm trust`

## package & skill management
- `project_pi_package_conventions.md` — Native Pi package standards for package.json, skills, extensions, worktrees, runtime deps — no Claude plugin artifacts
- `feedback_agents_skills_symlinks.md` — `~/.agents/skills/` entries are user symlinks to local dev repos — never delete them when cleaning skill installs
- `feedback_stale_session_skill_paths.md` — pi caches package/skill paths at session start; after a repo restructure old sessions throw ENOENT — restart pi
- `feedback_pipe_buffering_watch_filters.md` — grep/sed/awk block-buffer when piped; a monitor watching `script | grep -v` sees nothing — use native exclusion or --line-buffered

## package designs
- `project_teammate_autonomous_and_tui.md` — teammate: autonomous child Pi workers over a shared state file, blocking/background spawn, deps, worktree isolation, live polling, /teammate console
- `project_monitor_optimization.md` — pi-monitor bounds background-process output and uses `close` over `exit`; settled direction is result-contract monitoring, not raw-log streaming
- `project_vision_package_design.md` — vision bridge intercepts images only for text-only models and delegates to a configured vision model
