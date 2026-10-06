"""Real Pi print and PTY reproductions backed only by a loopback model server."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from native_support import NativeTui, records

REPO = Path(__file__).resolve().parents[3]


SHORT_RESULT = "2"
MULTILINE_RESULT = "FIRST_RESULT_LINE\n\nSECOND_RESULT_LINE"
LONG_RESULT = "word " * 55 + "REQUIRED_RESULT_TAIL"






def test_native_print_returns_once_and_parent_shutdown_closes_temporary_child(native_command: tuple, tmp_path: Path) -> None:
    command, env, snapshots, requests, release = native_command
    release.set()
    result = subprocess.run([*command, '--print'], cwd=tmp_path, env=env,
        input='', text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr + result.stdout
    events = records(snapshots)
    receipts = [event for event in events if event['kind'] == 'receipt']
    answers = [event for event in events if event['kind'] == 'result']
    assert len(receipts) == len(answers) == len(requests) == 1, events
    assert 'arrives automatically' in receipts[0]['content'][0]['text']
    assert receipts[0]['details']['session'].startswith('session:')
    assert answers[0]['options'] == {'deliverAs': 'followUp', 'triggerTurn': True}
    assert answers[0]['content'].endswith(env['PI_AGENT_RESULT_TEXT'] + '\n</agent-result>')
    assert answers[0]['details']['text'] == env['PI_AGENT_RESULT_TEXT']
    assert answers[0]['details']['turn'] == 1
    assert events[-1] == {'kind': 'shutdown', 'living': 0, 'results': 1}, events
    assert not any(event['kind'] == 'mount' for event in events)
    assert not (tmp_path / 'agent' / 'agents').exists()
    assert not (tmp_path / 'agent' / 'subagent-sessions').exists()


# Formatting axes belong here, not in every lifecycle/control reproduction.
@pytest.mark.parametrize("case,native_command", [
    ("default", SHORT_RESULT), ("default", MULTILINE_RESULT), ("interrupt-expansion", LONG_RESULT),
], indirect=["native_command"], ids=["short", "multiline", "steered-long"])
def test_native_tui_shows_activity_resizes_retains_idle_and_clears_on_shutdown(native_command: tuple, tmp_path: Path, case: str) -> None:
    command, env, snapshots, requests, release = native_command
    steering = "STEER_FIRST_LINE " + "steering " * 45 + "REQUIRED_STEER_TAIL"
    if case == "interrupt-expansion":
        env = {**env, "PI_AGENT_USAGE_CASE": case, "PI_AGENT_STEER_TEXT": steering}
    tui = NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=90)

    def widget_at(width: int) -> bool:
        return any(event['kind'] == 'widget' and event['width'] == width for event in records(snapshots))

    try:
        tui.wait_for(lambda: bool(requests) and 'calculator · Starting...' in tui.screen())
        model = 'subagents-local-fixture/arithmetic'
        collapsed = [event for event in records(snapshots)
            if event['kind'] == 'agent-row' and event.get('action') == 'agent_start' and not event['partial'] and not event['expanded']]
        assert collapsed, 'the native tool must render its settled startup receipt'
        assert all(model not in '\n'.join(event['lines']) for event in collapsed), collapsed
        assert f'model · {model}' not in tui.screen()
        # Native Ctrl+O expansion reveals exactly one model detail, while the
        # original model-facing receipt still contains its own configuration.
        if case == "interrupt-expansion":
            tui.wait_for(lambda: "NATIVE_INTERRUPT_READY" in tui.screen())
            steering_rows = [event for event in records(snapshots) if event['kind'] == 'agent-row'
                and event.get('action') == 'agent_input' and not event['partial'] and not event['expanded']]
            assert steering_rows, 'the steer receipt paints a row'
            # The collapsed steer row is its head line plus the authored headline,
            # so the affordance ends the head rather than the last line.
            for event in steering_rows:
                head = next((line.strip() for line in event['lines'] if line.strip()), '')
                assert head.startswith('[agent] steered · @calculator'), head
                assert re.search(r'to expand$', head), head
                assert 'REQUIRED_STEER_TAIL' not in '\n'.join(event['lines']), event['lines']
        tui.send(b'\x0f')
        tui.wait_for(lambda: any(event['kind'] == 'agent-row' and event.get('action') == 'agent_start' and event['expanded']
            for event in records(snapshots)))
        if case == "interrupt-expansion":
            # The steer row is expanded on screen; the fixture records it once the
            # next render happens, so the terminal is the authority here.
            tui.wait_for(lambda: 'REQUIRED_STEER_TAIL' in tui.screen())
            steering_rows = [event for event in records(snapshots) if event['kind'] == 'agent-row'
                and event.get('action') == 'agent_input' and event['expanded']]
            assert steering_rows and all(event['bounded'] for event in steering_rows)
            payload = [row for row in steering_rows if 'REQUIRED_STEER_TAIL' in '\n'.join(row['lines'])]
            assert payload, 'the expanded steer row carries the steer payload'
            row = '\n'.join(payload[-1]['lines'])
            assert row.count('REQUIRED_STEER_TAIL') == row.count('STEER_FIRST_LINE') == 1, row
            assert row.count('steering') == 45, row
            assert 'state · working' in row and 'next · runtime' in row, row
            assert 'session · session:' in row, row
            steered = next(event for event in records(snapshots)
            if event['kind'] == 'receipt' and event['details'].get('operation') == 'agent_input')
            assert steered['details']['prompt'] == steering and steered['structuredContent']['prompt'] == steering
        expanded = [event for event in records(snapshots)
            if event['kind'] == 'agent-row' and event.get('action') == 'agent_start' and not event['partial'] and event['expanded']]
        assert expanded and all(event['bounded'] for event in expanded)
        for event in expanded:
            row = '\n'.join(event['lines'])
            assert row.count(model) == 1, row
            assert f'model · {model}' in row and 'MODEL ·' not in row, row
        receipt = next(event for event in records(snapshots) if event['kind'] == 'receipt')
        assert f'Model: {model}' in receipt['content'][0]['text']
        assert receipt['details']['model'] == model
        tui.send(b'\x0f')
        for width in (48, 240):
            tui.resize(width)

            tui.wait_for(lambda: widget_at(width))
        events = records(snapshots)
        widgets = [event for event in events if event['kind'] == 'widget']
        assert widgets and all(event['bounded'] for event in widgets)
        assert any(event['kind'] == 'mount' and event['placement'] == 'aboveEditor' for event in events)
        assert all(not re.search(r'session:|[0-9a-f]{8}-[0-9a-f]{4}-', '\n'.join(event['lines'])) for event in widgets)
        tui.resize(90)

        release.set()
        tui.wait_for(lambda: 'SUBAGENT_RESULT_2' in tui.screen())
        # The child settled with its answer delivered, so it leaves the activity
        # area: only work in flight occupies it, and a stale row would imply work.
        # The child settled and its answer was delivered, so it leaves the activity
        # area: the newest widget snapshot must not mention it, and an unmounted
        # area counts as empty.
        def settled() -> bool:
            log = records(snapshots)
            delivered = next((index for index, event in enumerate(log)
                if event['kind'] == 'result'), None)
            if delivered is None:
                return False
            after = [event for event in log[delivered:] if event['kind'] == 'widget']
            return not any('calculator' in line for event in after for line in event['lines'])

        tui.wait_for(settled)
        # Steering can create another assistant response in the same sequence,
        # not a second child/input lifetime. Only the final settlement delivers.
        assert len(requests) == (2 if case == "interrupt-expansion" else 1)
        if case == "interrupt-expansion":
            assert steering in json.dumps(requests[-1], ensure_ascii=False)
        events = records(snapshots)
        assert len([event for event in events if event['kind'] == 'result']) == 1
        widget_events = [event for event in events if event['kind'] == 'widget']
        assert widget_events and all(event['bounded'] for event in widget_events), events
        assert settled(), [event for event in records(snapshots)[-4:]]
        result_text = env['PI_AGENT_RESULT_TEXT']
        answer_lines = [line for line in result_text.splitlines() if line.strip()]
        collapsed_results = [event for event in events if event['kind'] == 'result-row' and not event['expanded']]
        assert collapsed_results and all(event['bounded'] for event in collapsed_results), events
        for event in collapsed_results:
            row = '\n'.join(event['lines'])
            assert 'Session Result' not in row and not re.search(r'turn [0-9]', row), row
            visible = [line.strip() for line in event['lines'] if line.strip()]
            assert len(visible) == 1, visible
            assert visible[0].startswith('[agent] reported · @calculator'), visible
            assert re.search(r'to expand$', visible[0]), visible
            assert not any(line in row for line in answer_lines), 'the answer waits for expansion'
        marker = max((token for line in answer_lines for token in line.split()), key=len)
        tui.send(b'\x0f')
        if marker not in tui.screen():
            tui.send(b'\x0f')
        tui.wait_for(lambda: marker in tui.screen())
        # The terminal is the authority for the expanded body: a steer row and a
        # reported row share one expand key, so which snapshot records it is a race.
        screen = tui.screen()
        assert not re.search(r'\[agent\] reported · @calculator · \S*to expand', screen), screen[-2000:]
        assert all(token in screen for token in answer_lines[-1].split()[-2:]), screen[-2000:]
        expanded_results = [event for event in records(snapshots)
            if event['kind'] == 'result-row' and event['expanded']]
        assert all(event['bounded'] for event in expanded_results), expanded_results
        for event in expanded_results:
            row = '\n'.join(event['lines'])
            assert 'Session Result' not in row and 'to expand' not in row, row
            assert all(token in row for line in answer_lines for token in line.split()), row
        delivered = next(event for event in records(snapshots) if event['kind'] == 'result')
        assert delivered['details']['text'] == result_text and delivered['details']['turn'] == 1
        assert delivered['details']['session'].startswith('session:')
        tui.send(b'/quit\r')
        tui.wait_for(lambda: tui.process.poll() is not None)
        assert tui.process.returncode == 0
        assert any(event['kind'] == 'clear' for event in records(snapshots))
        assert records(snapshots)[-1] == {'kind': 'shutdown', 'living': 0, 'results': 1}
    finally:
        release.set()
        tui.close()


@pytest.mark.parametrize("interface", ["print", "tui"])
@pytest.mark.parametrize("diagnostic,case", [("", "stopped-inspect"),
    ("\x1b[31mNATIVE_ERROR_HEAD\x1b[0m\x07" + " x" * 12000 + "RAW_ERROR_TAIL", "stopped-inspect"),
    ("", "cancel-startup-wait"), ("", "codemode-lifecycle")],
    ids=["without-error", "long-retained-error", "cancel-startup-wait", "codemode-lifecycle"])
def test_native_roster_read_reports_retained_stopped_facts_not_a_failed_row(
    native_command: tuple, tmp_path: Path, interface: str, diagnostic: str, case: str,
) -> None:
    """Native lifecycle after a stop; invented retained error specifically probes
    the roster page's readback bounds. The roster page is a status summary, so it
    carries no per-child output preview: the answer arrives with the Session Result."""
    command, env, snapshots, requests, release = native_command
    env = {**env, "PI_AGENT_USAGE_CASE": case, "PI_AGENT_INSPECT_DIAGNOSTIC": diagnostic}
    release.set()
    if interface == "print":
        result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env,
            input="", text=True, capture_output=True, timeout=45)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "NATIVE_STOPPED_INSPECT_OK" in result.stdout, result.stdout + result.stderr
    else:
        tui = NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=90, timeout=45)
        try:
            tui.wait_for(lambda: "NATIVE_STOPPED_INSPECT_OK" in tui.screen())
            if case == "cancel-startup-wait":
                # No route came back, so no stop or roster row exists: the roster
                # read and the uncertain start row are the whole witness.
                assert "[agent] uncertain · @calculator" in tui.screen(), tui.screen()
                assert "[agent] listed · @children" in tui.screen(), tui.screen()
            elif case != "codemode-lifecycle":
                # A roster subject carries the page count and no child's state, so
                # the collapsed row never names the child it read.
                assert "[agent] listed · @children · 1 of 1" in tui.screen(), tui.screen()
                assert "[agent] listed · @calculator" not in tui.screen(), tui.screen()
            else:
                # Native codemode uses Pi's own unbracketed title, not pi-kit.
                assert "codemode" in tui.screen() and "Script error:" not in tui.screen(), tui.screen()
            assert "No living session" not in tui.screen(), tui.screen()
            if case != "cancel-startup-wait":
                assert "[agent] failed" not in tui.screen(), tui.screen()
            else:
                assert "cancelled" in tui.screen(), tui.screen()
            if case != "codemode-lifecycle":
                tui.send(b"\x0f")
                tui.wait_for(lambda: any(event["kind"] == "agent-row"
                    and event.get("action") == "agent_list" and event["expanded"]
                    for event in records(snapshots)))
                rows = [event for event in records(snapshots) if event["kind"] == "agent-row"
                    and event.get("action") == "agent_list"]
                assert rows and all(event["bounded"] for event in rows), rows
                assert all("[agent] " in "\n".join(event["lines"]) for event in rows), rows
                # The page keeps the child's own status as expansion detail, naming
                # the child once, and the collapsed subject stays the page.
                collapsed = [event for event in rows if not event["expanded"]]
                assert collapsed and all("@calculator" not in "\n".join(event["lines"]) for event in collapsed), collapsed
                expanded = [event for event in rows if event["expanded"]]
                assert expanded, rows
                headers = [line.strip() for event in expanded for line in event["lines"] if "@calculator · " in line]
                assert headers and all(header.count("@calculator") == 1 for header in headers), headers
                if case != "cancel-startup-wait":
                    assert "@calculator · stopped" in headers, headers
            tui.send(b"/quit\r")
            tui.wait_for(lambda: tui.process.poll() is not None)
            assert tui.process.returncode == 0
        finally:
            tui.close()
    events = records(snapshots)
    receipts = [event for event in events if event["kind"] == "receipt"]
    if case == "cancel-startup-wait":
        # A cancelled start returns no route, so the only follow-up a caller can make
        # is the roster read. It has to show the child the cancellation could not.
        assert [event["details"]["operation"] for event in receipts] == ["agent_start", "agent_list"], receipts
        assert receipts[0]["details"]["disposition"] == "uncertain" and receipts[0]["isError"] is True
        assert receipts[0]["details"]["controlOutcome"] == "uncertain"
        listed, = receipts[1]["details"]["sessions"]
        assert listed["label"] == "calculator", listed
        cancelled, = [event for event in events if event["kind"] == "cancelled-native-start"]
        assert cancelled["living"] == 1 and cancelled["details"]["dispatched"] is True
        assert not receipts[1]["isError"]
        assert events[-1] == {"kind": "shutdown", "living": 0, "results": 1}
        return
    assert [event["details"]["operation"] for event in receipts] == ["agent_start", "agent_stop", "agent_list"], receipts
    assert receipts[0]["details"]["ok"] and not receipts[0]["isError"], receipts
    assert all(event["details"]["ok"] and not event["isError"] for event in receipts[1:]), receipts
    for event in receipts:
        assert event["structuredContent"]["operation"] == event["details"]["operation"]
        assert event["structuredContent"]["disposition"] == event["details"]["disposition"]
        assert event["structuredContent"]["ok"] == event["details"]["ok"]
    started, stopped, listed = [event["details"] for event in receipts]
    view, = listed["sessions"]
    assert view["status"] == "stopped" and view["session"] == started["session"] == stopped["session"]
    assert view["label"] == "calculator", view
    assert view["resultKind"] == "result" and view["sequenceEnded"] is True
    # The roster page is a status summary. It omits the output preview on purpose,
    # because a child's complete answer arrives with its Session Result.
    assert "liveText" not in view and "liveText" in view["truncation"]["omittedFields"], view
    # One page, one child, and the page says which part of the roster it holds.
    assert listed["page"]["returned"] == 1 and listed["page"]["remaining"] == 0, listed["page"]
    assert listed["page"]["totalSessions"] + listed["page"]["totalDefinitions"] == 1, listed["page"]
    preservation, = [event for event in events if event["kind"] == "inspect-preservation"]
    assert preservation == {"kind": "inspect-preservation", "unchanged": True,
        "rawErrorLength": len(diagnostic), "errorRetained": True}
    if diagnostic:
        expected = ("NATIVE_ERROR_HEAD" + " x" * 12000 + "RAW_ERROR_TAIL")[:1000] + "… [diagnostic truncated]"
        assert view["error"] == expected
        listed_event = receipts[-1]
        assert "error · " + expected in listed_event["content"][0]["text"]
        assert "RAW_ERROR_TAIL" not in json.dumps(listed_event)
        assert "\x1b" not in listed_event["content"][0]["text"] and "\x07" not in listed_event["content"][0]["text"]
    else:
        assert "error" not in view
    assert len(requests) == 1, "The roster read must not start another model request or revive the child"
    assert len([event for event in events if event["kind"] == "result"]) == 1
    assert events[-1] == {"kind": "shutdown", "living": 0, "results": 1}
    assert not (tmp_path / "agent" / "agents").exists()
    assert not (tmp_path / "agent" / "subagent-sessions").exists()
