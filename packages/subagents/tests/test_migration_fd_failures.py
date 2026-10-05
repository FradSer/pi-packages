"""Descriptor fault chains preserve first failure and disclose unverified files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from identity_support import LEGACY, run


@pytest.mark.parametrize("operation", ["write", "fsync", "close-only"])
def test_migration_fd_close_failure_preserves_original_cause_and_cleanup(tmp_path: Path, operation: str) -> None:
    result = run(LEGACY + f'''
      const {{syncBuiltinESMExports}}=await import("node:module");
      const plan=sa.planAgentMigration(options),destinations=plan.files.map(file=>file.destination);
      const primary=Object.assign(new Error("primary migration failure"),{{code:"EIO"}});
      const closing=Object.assign(new Error("descriptor close failure"),{{code:"EBADF"}});
      const real={{openSync:fs.openSync,writeFileSync:fs.writeFileSync,fsyncSync:fs.fsyncSync,closeSync:fs.closeSync}};
      const descriptors=new Map(),closed=[];const selected=destinations.at(-1);
      const operation={json.dumps(operation)};let caught;
      fs.openSync=(file,...args)=>{{const fd=real.openSync(file,...args);if(destinations.includes(file))descriptors.set(fd,file);return fd;}};
      fs.writeFileSync=(fd,...args)=>{{
        if(descriptors.get(fd)===selected&&operation==="write"){{real.writeFileSync(fd,"PARTIAL");throw primary;}}
        return real.writeFileSync(fd,...args);
      }};
      fs.fsyncSync=fd=>{{if(descriptors.get(fd)===selected&&operation==="fsync")throw primary;return real.fsyncSync(fd);}};
      fs.closeSync=fd=>{{
        const file=descriptors.get(fd);if(file)closed.push(file);
        real.closeSync(fd);
        if(file===selected)throw closing;
      }};
      syncBuiltinESMExports();
      try{{sa.applyAgentMigration(plan);}}catch(error){{caught=error;}}
      finally{{Object.assign(fs,real);syncBuiltinESMExports();}}
      const expected=operation==="close-only"?closing:primary;
      console.log(JSON.stringify({{aggregate:caught instanceof AggregateError,
        originalCause:caught?.cause===expected,first:caught?.errors?.[0]===expected,
        closeCause:caught?.errors?.some(error=>error.cause===closing),message:caught?.message,
        selected,closed,remaining:destinations.filter(file=>fs.existsSync(file)),originalsKept:originalsKept()}}));
    ''', tmp_path, migration=True)
    assert result["aggregate"] is True, result
    assert result["originalCause"] is True and result["first"] is True, result
    assert result["closeCause"] is True
    assert result["selected"] in result["message"]
    assert "close" in result["message"].lower() and "descriptor" in result["message"].lower()
    assert result["closed"].count(result["selected"]) == 1
    assert result["remaining"] == [] and result["originalsKept"] is True


@pytest.mark.parametrize("target_index", [0, -1])
@pytest.mark.parametrize("replacement", ["none", "file", "symlink"])
@pytest.mark.parametrize("close_fails", [False, True])
def test_migration_fstat_failure_discloses_unknown_ownership_without_blind_unlink(
    tmp_path: Path, replacement: str, close_fails: bool, target_index: int,
) -> None:
    result = run(LEGACY + f'''
      const {{syncBuiltinESMExports}}=await import("node:module");
      const plan=sa.planAgentMigration(options),destinations=plan.files.map(file=>file.destination);
      const primary=Object.assign(new Error("descriptor ownership inspection failed"),{{code:"EIO"}});
      const closing=Object.assign(new Error("descriptor close also failed"),{{code:"EBADF"}});
      const real={{openSync:fs.openSync,fstatSync:fs.fstatSync,closeSync:fs.closeSync,unlinkSync:fs.unlinkSync}};
      const descriptors=new Map(),closed=[],removed=[];const selected=destinations.at({target_index});
      const replacement={json.dumps(replacement)},closeFails={json.dumps(close_fails)};
      const outside=path.join(cwd,"unrelated-target"),held=path.join(cwd,"held-created-inode");
      put(outside,"UNRELATED");let caught;
      fs.openSync=(file,...args)=>{{const fd=real.openSync(file,...args);if(destinations.includes(file))descriptors.set(fd,file);return fd;}};
      fs.fstatSync=(fd,...args)=>{{
        if(descriptors.get(fd)===selected){{
          if(replacement!=="none"){{fs.renameSync(selected,held);if(replacement==="file")put(selected,"REPLACEMENT");else fs.symlinkSync(outside,selected);}}
          throw primary;
        }}
        return real.fstatSync(fd,...args);
      }};
      fs.closeSync=fd=>{{const file=descriptors.get(fd);if(file)closed.push(file);real.closeSync(fd);if(file===selected&&closeFails)throw closing;}};
      fs.unlinkSync=(file,...args)=>{{if(destinations.includes(file))removed.push(file);return real.unlinkSync(file,...args);}};
      syncBuiltinESMExports();
      try{{sa.applyAgentMigration(plan);}}catch(error){{caught=error;}}
      finally{{Object.assign(fs,real);syncBuiltinESMExports();}}
      console.log(JSON.stringify({{aggregate:caught instanceof AggregateError,originalCause:caught?.cause===primary,
        first:caught?.errors?.[0]===primary,closeCause:caught?.errors?.some(error=>error.cause===closing),
        message:caught?.message,selected,closed,removed,
        remaining:destinations.filter(file=>fs.existsSync(file)),originalsKept:originalsKept(),
        selectedText:fs.readFileSync(selected,"utf8"),symlink:fs.lstatSync(selected).isSymbolicLink(),
        outside:fs.readFileSync(outside,"utf8")}}));
    ''', tmp_path, migration=True)
    assert result["aggregate"] is True and result["originalCause"] is True and result["first"] is True, result
    assert result["closeCause"] is close_fails
    assert result["selected"] in result["message"]
    assert "ownership" in result["message"].lower() and "incomplete" in result["message"].lower()
    assert result["remaining"] == [result["selected"]]
    assert result["selected"] not in result["removed"]
    assert result["closed"].count(result["selected"]) == 1
    assert result["selectedText"] == ("" if replacement == "none" else "REPLACEMENT" if replacement == "file" else "UNRELATED")
    assert result["symlink"] is (replacement == "symlink")
    assert result["outside"] == "UNRELATED" and result["originalsKept"] is True
