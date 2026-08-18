from __future__ import annotations

import json
import os
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
GLOBAL_SESSIONS_URI = (SRC / "global-sessions.ts").as_uri()
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
    assert "Scenario: User activates thread and marks message as read" in feature
    assert "Scenario: User activates thread while another session is running" in feature
    assert "Scenario: User manual abort does not trigger red error light" in feature
    assert "Scenario: All sessions must be read for unread green light to clear" in feature
    assert "Scenario: Pi transitions to thinking state with blue breathing light" in feature
    assert "Scenario: Pi transitions to need approval state with yellow blinking light" in feature
    assert "Scenario: Pi transitions to error state with red blinking light" in feature
    assert "Scenario: Non-fatal tool errors do not trigger red blinking light" in feature
    assert "Scenario: Upstream provider rate limit (429) triggers red blinking error light" in feature
    assert "Scenario: User submits input and clears unread chat status" in feature
    assert "Scenario: Orphaned unread record from an unexpectedly-exited session is cleaned up" in feature
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
    assert result["thinking"]["hue"] == 165  # Softened oceanic blue
    assert result["thinking"]["sat"] == 210  # Softened saturation
    assert result["thinking"]["pattern"] == "breathing"
    assert result["thinking"]["effect"] == 2
    assert result["thinking"]["smoothRamp"] is True

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

        let mockOtherUnread = false;
        let mockOtherRunning = false;

        const sm = new KeyboardStateMachine(
            {{
                enabled: false,
                zone: "all",
                brightnessScale: 1.0,
                saveToEeprom: false,
            }},
            "test-session-1",
            "/tmp/test-cwd",
            (id, selfRec) => {{
                let effectiveState = "idle";
                if (selfRec.status === "error") {{
                    effectiveState = "error";
                }} else if (selfRec.status === "need_approval") {{
                    effectiveState = "need_approval";
                }} else if (selfRec.hasUnread || mockOtherUnread) {{
                    effectiveState = "unread_chat";
                }} else if (selfRec.status === "running" || mockOtherRunning) {{
                    effectiveState = "thinking";
                }}
                return {{
                    effectiveState,
                    hasAnyUnread: selfRec.hasUnread || mockOtherUnread,
                    hasAnyRunning: selfRec.status === "running" || mockOtherRunning,
                    hasAnyError: selfRec.status === "error",
                    hasAnyNeedApproval: selfRec.status === "need_approval",
                    activeSessionCount: 1,
                }};
            }},
        );

        const history = [];

        // 1. Session start -> idle (white)
        await sm.onSessionStart();
        history.push(sm.getCurrentState());

        // 2. Agent start -> thinking (blue)
        await sm.onAgentStart();
        history.push(sm.getCurrentState());

        // 3. Bash command error -> stays thinking (blue)
        await sm.onToolCall("bash", {{ command: "grep nonexistent file" }});
        await sm.onToolResult();
        history.push(sm.getCurrentState());

        // 4. User manual abort (Ctrl+C) -> returns to idle (white, NOT red!)
        await sm.onMessageEnd("aborted");
        history.push(sm.getCurrentState());

        // 5. Agent starts again -> thinking (blue)
        await sm.onAgentStart();
        history.push(sm.getCurrentState());

        // 6. Normal finish -> unread_chat (green)
        await sm.onAgentSettled(false);
        history.push(sm.getCurrentState());

        // 7. User activates thread while another session HAS unread -> stays green unread_chat
        mockOtherUnread = true;
        await sm.onUserActivated();
        history.push(sm.getCurrentState());

        // 8. User activates thread when ALL sessions are read -> becomes idle (white)
        mockOtherUnread = false;
        mockOtherRunning = false;
        await sm.onUserActivated();
        history.push(sm.getCurrentState());

        // 9. Upstream provider 429 error occurs -> error (red blinking)
        await sm.onProviderResponse(429);
        history.push(sm.getCurrentState());

        // 10. Agent settled after error keeps error state (never turns green)
        await sm.onAgentSettled(false);
        history.push(sm.getCurrentState());

        console.log(JSON.stringify({{ history }}));
        """
    )
    expected = [
        "idle",           # 1. onSessionStart
        "thinking",       # 2. onAgentStart
        "thinking",       # 3. toolResult
        "idle",           # 4. onMessageEnd("aborted") -> idle, NOT red!
        "thinking",       # 5. onAgentStart
        "unread_chat",    # 6. onAgentSettled -> unread_chat (green)
        "unread_chat",    # 7. onUserActivated while other session unread -> stays unread_chat (green)
        "idle",           # 8. onUserActivated when all sessions read -> idle (white)
        "error",          # 9. onProviderResponse(429) -> error (red blinking)
        "error",          # 10. onAgentSettled preserves error
    ]
    assert result["history"] == expected


def test_orphaned_unread_records_from_dead_sessions_are_pruned() -> None:
    # A session that was unread and then exited unexpectedly (crash / kill / terminal
    # closed without a clean shutdown) leaves an orphaned settled/unread glow record.
    # pruneOrphanedGlowStates must remove those (so stale green does not pile up)
    # while keeping records of live sessions.
    import subprocess as sp
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        # Use this pytest process's own PID as the "live" session to guarantee it is alive.
        live_pid = os.getpid()
        # A PID that is guaranteed dead for the sweep: spawn a short-lived child and let it exit.
        dead_marker = Path(tmp) / "dead.pid"
        subprocess.run(["sh", "-c", f"echo $$ > {dead_marker}"], check=True)
        dead_pid = int(dead_marker.read_text().strip())

        # Give the child a moment to fully exit so signal 0 reports it as dead.
        import time
        time.sleep(0.05)

        # Layout mirrors getSessionFileKey(cwd): a per-cwd directory holding session files.
        cwd_dir = Path(tmp) / "--tmp-test-cwd--"
        cwd_dir.mkdir(parents=True, exist_ok=True)
        (cwd_dir / "live-session.json").write_text(
            json.dumps({"sessionId": "live", "pid": live_pid, "cwd": "/tmp", "status": "settled", "hasUnread": True, "updatedAt": 123456}),
            encoding="utf-8",
        )
        (cwd_dir / "dead-session.json").write_text(
            json.dumps({"sessionId": "dead", "pid": dead_pid, "cwd": "/tmp", "status": "settled", "hasUnread": True, "updatedAt": 123456}),
            encoding="utf-8",
        )

        script = f"""
        import {{ pruneOrphanedGlowStates }} from "{GLOBAL_SESSIONS_URI}";
        const removed = pruneOrphanedGlowStates();
        console.log(JSON.stringify({{ removed }}));
        """
        env = {**os.environ, "PI_DIRECTORY_SESSIONS_DIR": tmp}
        result = sp.run(
            ["node", "--import", "tsx", "--input-type=module"],
            cwd=REPO,
            input=textwrap.dedent(script),
            text=True,
            capture_output=True,
            timeout=15,
            env=env,
        )
        assert result.returncode == 0, f"prune test failed:\n{result.stderr}\n{result.stdout}"
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
        assert parsed["removed"] == 1
        assert (cwd_dir / "dead-session.json").exists() is False
        assert (cwd_dir / "live-session.json").exists() is True


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
    assert "after_provider_response" in events
    assert "tool_call" in events
    assert "tool_result" in events
    assert "message_end" in events
    assert "turn_end" in events
    assert "agent_settled" in events
    assert "input" in events
    assert "session_shutdown" in events
    assert result["registeredCommands"] == ["keyboard"]
