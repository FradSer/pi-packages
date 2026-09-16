"""Reload archives incompatible Work state without breaking extension initialization."""

import json
import os
import subprocess
import textwrap

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_incompatible_snapshot_is_archived_and_initialization_continues(tmp_path):
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(f'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ boardFilePath }} from "./src/statefile.ts";
        import {{ initTeamMachine, shutdownTeamMachine }} from "./src/team-machine.ts";
        const cwd = {str(tmp_path)!r};
        const board = boardFilePath(undefined, cwd);
        fs.mkdirSync(board.slice(0, board.lastIndexOf("/")), {{ recursive: true }});
        fs.writeFileSync(board, JSON.stringify({{ runtimeVersion: 1, tasks: {{ "old-work": {{ id: "old-work" }} }} }}));
        initTeamMachine({{ sessionManager: undefined, cwd }}, {{ sendUpdate() {{}}, notifyChange() {{}} }});
        const archived = fs.readdirSync(board.slice(0, board.lastIndexOf("/"))).find((name) => name.startsWith("board.json.incompatible-"));
        assert.ok(archived);
        assert.equal(fs.existsSync(board), false);
        shutdownTeamMachine();
        console.log(JSON.stringify({{ archived }}));
        ''')],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "board.json.incompatible-" in result.stdout
