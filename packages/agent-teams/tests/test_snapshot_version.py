import json
import os
import subprocess
import textwrap

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_incompatible_board_snapshot_raises_explicit_error(tmp_path):
    board = tmp_path / "board.json"
    board.write_text(json.dumps({"runtimeVersion": 1, "tasks": {"old": {}}}))
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(f'''
        import {{ readBoardFile }} from "@fradser/pi-tasks";
        try {{ readBoardFile({str(board)!r}); }} catch (error) {{ console.log(error.message); }}
        ''')],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # Wording changed when the board moved to @fradser/pi-tasks: the file is a Work
    # snapshot, and this package may be installed without the team runtime, so
    # naming Agent Teams in the error would be wrong. The version numbers and
    # the refusal to treat an incompatible board as empty are unchanged.
    assert "Incompatible Work snapshot version 1; expected 2." in result.stdout
