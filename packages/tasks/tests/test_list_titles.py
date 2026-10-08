"""Task lists use compact summaries with complete wrapped titles by default."""
from pathlib import Path

from test_task_contents import run


def test_default_list_is_compact_and_expansion_wraps_complete_titles(tmp_path: Path) -> None:
    result = run(
        r"""
        const subject="Verify storage behavior across restart boundaries and retain every meaningful title word FINAL_TITLE_WORD";
        await checked("create_task", {subject,description:"PRIVATE_DESCRIPTION_NOT_A_TITLE"});
        const listed=await checked("list_tasks",{});
        const observations=[32,80].map(width=>{
          const collapsed=render("list_tasks",listed,false,width);
          const expanded=render("list_tasks",listed,true,width);
          return {
            width,
            collapsed,
            expanded,
            collapsedText:collapsed.map(line=>line.trim()).join(" "),
            expandedText:expanded.map(line=>line.trim()).join(" "),
            widths:[...collapsed,...expanded].map(visibleWidth),
          };
        });
        console.log(JSON.stringify({subject,observations}));
        """,
        tmp_path,
    )
    for observed in result["observations"]:
        assert "Verify storage" in observed["collapsedText"]
        assert "FINAL_TITLE_WORD" in observed["collapsedText"]
        assert "FINAL_TITLE_WORD" in observed["expandedText"]
        assert "PRIVATE_DESCRIPTION_NOT_A_TITLE" not in observed["expandedText"]
        assert all(width <= observed["width"] for width in observed["widths"])
