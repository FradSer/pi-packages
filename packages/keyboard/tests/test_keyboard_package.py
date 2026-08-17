from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"
TYPES_URI = (SRC / "types.ts").as_uri()
PROTOCOL_URI = (SRC / "protocol.ts").as_uri()
CONFIG_URI = (SRC / "config.ts").as_uri()
STATE_MACHINE_URI = (SRC / "state-machine.ts").as_uri()
INDEX_URI = (SRC / "index.ts").as_uri()


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_feature_covers_keyboard_scenarios() -> None:
    feature = (PACKAGE / "features" / "keyboard.feature").read_text(encoding="utf-8")
    assert "Feature: Pi Keyboard Lighting Indicator" in feature
    assert "Scenario: Pi transitions to idle state with white breathing light" in feature
    assert "Scenario: Pi transitions to unread chat state with green breathing light" in feature
    assert "Scenario: Pi transitions to thinking state with blue breathing light" in feature
    assert "Scenario: Pi transitions to need approval state with yellow blinking light" in feature
    assert "Scenario: Pi transitions to error state with red blinking light" in feature
    assert "Scenario: Non-fatal tool errors do not trigger red blinking light" in feature
    assert "Scenario: User submits input and clears unread chat status" in feature
    assert "Scenario: Target lighting zone selection" in feature
    assert "Scenario: In-memory updates without EEPROM wear" in feature
    assert "Scenario: State change deduplication prevents redundant HID writes" in feature
    assert "Scenario: Keyboard disconnection handling" in feature
    assert "Scenario: /keyboard command allows manual state testing and toggle" in feature


def test_state_definitions_match_requirements() -> None:
    result = run_typescript(
        f"""
        import {{ KEYBOARD_STATE_DEFINITIONS }} from "{TYPES_URI}";

        const states = KEYBOARD_STATE_DEFINITIONS;
        console.log(JSON.stringify({{
            idle: states.idle,
            unread: states.unread_chat,
            thinking: states.thinking,
            approval: states.need_approval,
            error: states.error,
        }}));
        """
    )
    # Idle: White Breathing
    assert result["idle"]["sat"] == 0  # White
    assert result["idle"]["pattern"] == "breathing"
    assert result["idle"]["effect"] == 2

    # Unread: Green Breathing
    assert result["unread"]["hue"] == 85  # Green
    assert result["unread"]["pattern"] == "breathing"
    assert result["unread"]["effect"] == 2

    # Thinking: Blue Breathing
    assert result["thinking"]["hue"] == 170  # Blue
    assert result["thinking"]["pattern"] == "breathing"
    assert result["thinking"]["effect"] == 2

    # Need Approval / Question: Yellow Blinking
    assert result["approval"]["hue"] == 43  # Yellow
    assert result["approval"]["pattern"] == "blinking"

    # Error: Red Blinking
    assert result["error"]["hue"] == 0  # Red
    assert result["error"]["sat"] == 255
    assert result["error"]["pattern"] == "blinking"


def test_protocol_packet_construction() -> None:
    result = run_typescript(
        f"""
        import {{
            buildSetBrightnessPacket,
            buildSetEffectPacket,
            buildSetSpeedPacket,
            buildSetColorPacket,
            buildSavePacket,
            resolveChannels,
        }} from "{PROTOCOL_URI}";

        const bPacket = Array.from(buildSetBrightnessPacket(3, 200));
        const ePacket = Array.from(buildSetEffectPacket(3, 2));
        const sPacket = Array.from(buildSetSpeedPacket(3, 150));
        const cPacket = Array.from(buildSetColorPacket(3, 85, 255));
        const savePacket = Array.from(buildSavePacket(3));

        const allCh = resolveChannels("all");
        const matrixCh = resolveChannels("matrix");
        const underglowCh = resolveChannels("underglow");

        console.log(JSON.stringify({{
            bPacket,
            ePacket,
            sPacket,
            cPacket,
            savePacket,
            allCh,
            matrixCh,
            underglowCh,
        }}));
        """
    )
    # Set Value command is 0x07
    assert result["bPacket"][0] == 7 and result["bPacket"][1] == 3 and result["bPacket"][2] == 1 and result["bPacket"][3] == 200
    assert result["ePacket"][0] == 7 and result["ePacket"][1] == 3 and result["ePacket"][2] == 2 and result["ePacket"][3] == 2
    assert result["sPacket"][0] == 7 and result["sPacket"][1] == 3 and result["sPacket"][2] == 3 and result["sPacket"][3] == 150
    assert result["cPacket"][0] == 7 and result["cPacket"][1] == 3 and result["cPacket"][2] == 4 and result["cPacket"][3] == 85 and result["cPacket"][4] == 255
    assert result["savePacket"][0] == 9 and result["savePacket"][1] == 3
    assert result["allCh"] == [2, 3]
    assert result["matrixCh"] == [3]
    assert result["underglowCh"] == [2]


def test_state_machine_lifecycle_transitions() -> None:
    result = run_typescript(
        f"""
        import {{ KeyboardStateMachine }} from "{STATE_MACHINE_URI}";

        const sm = new KeyboardStateMachine({{
            enabled: false,
            zone: "all",
            brightnessScale: 1.0,
            saveToEeprom: false,
        }});

        const history = [];

        await sm.onSessionStart();
        history.push(sm.getCurrentState());

        await sm.onAgentStart();
        history.push(sm.getCurrentState());

        // Bash command running and failing (exit 1) should STAY in thinking
        await sm.onToolCall("bash", {{ command: "grep nonexistent file" }});
        history.push(sm.getCurrentState());

        await sm.onToolResult();
        history.push(sm.getCurrentState());

        // Interactive tool call transitions to need_approval
        await sm.onToolCall("confirm_action", {{}});
        history.push(sm.getCurrentState());

        // Normal settle transitions to unread_chat
        await sm.onAgentSettled(false);
        history.push(sm.getCurrentState());

        // User input clears unread
        await sm.onUserInput();
        history.push(sm.getCurrentState());

        // Fatal error stops Pi and transitions to error
        await sm.onMessageEnd("error");
        history.push(sm.getCurrentState());

        console.log(JSON.stringify({{ history }}));
        """
    )
    expected = [
        "idle",           # onSessionStart
        "thinking",       # onAgentStart
        "thinking",       # toolCall (bash)
        "thinking",       # toolResult (bash error does NOT make it red)
        "need_approval",  # interactive toolCall
        "unread_chat",    # onAgentSettled
        "idle",           # onUserInput
        "error",          # onMessageEnd("error")
    ]
    assert result["history"] == expected


def test_extension_registers_expected_hooks() -> None:
    result = run_typescript(
        f"""
        import extensionModule from "{INDEX_URI}";
        const extensionFn = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

        const registeredEvents = [];
        const registeredCommands = [];

        const fakePi = {{
            on(eventName, handler) {{
                registeredEvents.push(eventName);
            }},
            registerCommand(commandName, options) {{
                registeredCommands.push(commandName);
            }},
        }};

        extensionFn(fakePi);

        console.log(JSON.stringify({{ registeredEvents, registeredCommands }}));
        """
    )
    events = set(result["registeredEvents"])
    assert "session_start" in events
    assert "agent_start" in events
    assert "turn_start" in events
    assert "tool_call" in events
    assert "tool_result" in events
    assert "message_end" in events
    assert "agent_settled" in events
    assert "input" in events
    assert "session_shutdown" in events
    assert result["registeredCommands"] == ["keyboard"]
