"""Behavior contract for @features/impeccable-live.feature."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]


LIVE_GUIDANCE = (
    "On macOS, launch the served application with `open <served app URL>`; never open the helper "
    "`serverPort` and never use agent-browser. After the page connects, keep one foreground "
    "`live-poll.mjs` process active."
)


def test_impeccable_live_guidance_is_injected_only_for_matching_expanded_user_message(tmp_path: Path) -> None:
    project = tmp_path / "project"
    agent_dir = tmp_path / "isolated-agent"
    (project / ".pi").mkdir(parents=True)
    (agent_dir / "memory").mkdir(parents=True)
    (project / ".pi" / "harness.json").write_text(
        json.dumps(
            {
                "skillPrompts": {
                    "impeccable": {
                        "prompt": LIVE_GUIDANCE,
                        "target": "system",
                        "userMessagePattern": "^live$",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (agent_dir / "memory" / "settings.json").write_text('{"autoMemory": false}\n', encoding="utf-8")

    result = subprocess.run(
        [
            "bun",
            "-e",
            f"""
            import {{ parseSkillBlock }} from "@earendil-works/pi-coding-agent";

            const hooks = {{}};
            const pi = {{
              on: (name, handler) => (hooks[name] ??= []).push(handler),
              registerCommand: () => {{}},
              registerEntryRenderer: () => {{}},
              appendEntry: () => {{}},
            }};
            const extension = await import("./packages/continual-learning/index.ts");
            extension.default(pi);

            const expanded = (userMessage) =>
              `<skill name="impeccable" location="/skills/impeccable/SKILL.md">\\nSkill body\\n</skill>\\n\\n${{userMessage}}`;
            const invokeBeforeAgentStart = async (userMessage) => {{
              let systemPrompt = "base system";
              for (const handler of hooks.before_agent_start ?? []) {{
                const result = await handler({{
                  type: "before_agent_start",
                  prompt: expanded(userMessage),
                  images: undefined,
                  systemPrompt,
                  systemPromptOptions: {{}},
                }}, {{ cwd: {json.dumps(str(project))}, hasUI: false }});
                if (result?.systemPrompt !== undefined) systemPrompt = result.systemPrompt;
              }}
              return systemPrompt;
            }};

            const livePrompt = expanded("live");
            const polishPrompt = expanded("polish");
            console.log(JSON.stringify({{
              liveUserMessage: parseSkillBlock(livePrompt)?.userMessage,
              polishUserMessage: parseSkillBlock(polishPrompt)?.userMessage,
              liveSystemPrompt: await invokeBeforeAgentStart("live"),
              polishSystemPrompt: await invokeBeforeAgentStart("polish"),
            }}));
            """,
        ],
        cwd=REPO,
        env={**os.environ, "PI_CODING_AGENT_DIR": str(agent_dir)},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout.strip())

    assert output["liveUserMessage"] == "live"
    assert output["polishUserMessage"] == "polish"
    assert output["liveSystemPrompt"] == f"base system\n\n{LIVE_GUIDANCE}"
    assert output["polishSystemPrompt"] == "base system"
