"""Default task list preserves stored titles, not description previews."""
from pathlib import Path

from test_task_contents import run


def test_default_list_wraps_complete_titles(tmp_path: Path) -> None:
    result = run(
        r"""
        const subject="Verify storage behavior across restart boundaries and retain every meaningful title word FINAL_TITLE_WORD";
        await checked("create_task", {subject,description:"PRIVATE_DESCRIPTION_NOT_A_TITLE"});
        const listed=await checked("list_tasks",{});
        const observations=[32,80].map(width=>{
          const lines=render("list_tasks",listed,false,width);
          return {width,lines,widths:lines.map(visibleWidth),text:lines.map(line=>line.trim()).join(" ")};
        });
        console.log(JSON.stringify({subject,observations}));
        """,
        tmp_path,
    )
    for observed in result["observations"]:
        assert "FINAL_TITLE_WORD" in observed["text"]
        assert "…" not in observed["text"]
        assert "PRIVATE_DESCRIPTION_NOT_A_TITLE" not in observed["text"]
        assert all(width <= observed["width"] for width in observed["widths"])
