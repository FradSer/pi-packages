"""SDK loading is optional; an enabled required review must still fail closed.

Legacy injected judges retain their contract. The normal parent requires complete
coverage proof when semantic Memory review is enabled, including SDK absence.
"""
from __future__ import annotations

from pathlib import Path

from support import run_bun_script

HARNESS = Path(__file__).with_name("learning-policy-harness.ts")
ENTRY_HARNESS = Path(__file__).with_name("sdk-absence-harness.ts")
ABSENT = {"CL_ABSENT_TYPESAFE_SDK": "1"}


def memory_attempts(value: dict) -> list[dict]:
    receipt = value.get("registryReceipt") or {}
    return [attempt for attempt in (receipt.get("attempts") or []) if attempt.get("phase") == "memory"]


def test_the_package_entry_loads_and_registers_without_the_typesafe_sdk() -> None:
    # Given the TypeSafe SDK unresolvable, When the package entry loads, Then the
    # extension still registers its commands and hooks instead of failing the load.
    value = run_bun_script(ENTRY_HARNESS, env=ABSENT)
    # The load result is asserted first, so a run against a static SDK import reports
    # the load failure rather than a later assertion about the absence probe.
    assert value["loaded"] is True, value
    assert value["failure"] is None, value
    assert value["registrations"] > 0, value
    assert {"on", "registerCommand"} <= set(value["registrationKinds"])


def test_a_substituted_judge_still_learns_memory_without_the_typesafe_sdk() -> None:
    # Given the SDK unresolvable and a judge supplied by its seam, When a real
    # learning run settles, Then the pipeline writes the proven records. This is
    # what pluggable means: the judge is replaceable and the SDK is not required.
    value = run_bun_script(HARNESS, "remember-subset", env={**ABSENT, "CL_JEV_FIXTURE": "subset-composed"})
    assert value["registryReceipt"]["operations"] == 2
    assert {"tools.md", "license.md"} <= set(value["privateFiles"])
    assert {"tools.md", "license.md"} <= set(value["publicFiles"])
    assert not value["lock"]


def test_an_enabled_parent_review_keeps_proposals_without_the_sdk() -> None:
    # Given the SDK is absent and semantic review is enabled, When the parent
    # settles, Then it retains the plan and coverage cost without authorizing writes.
    value = run_bun_script(HARNESS, "remember-subset", env={**ABSENT, "TYPESAFE_API_KEY": "fixture-absent-sdk"})
    attempts = memory_attempts(value)
    semantic = [attempt for attempt in attempts if "jev" in attempt]
    assert len(semantic) == 1, attempts
    assert semantic[0]["jev"]["reason"] == "unavailable"
    assert semantic[0]["jev"].get("model") is None
    assert semantic[0]["jev"]["requestCount"] == 0
    assert semantic[0]["outcome"] == "proposed"
    assert value["registryReceipt"]["operations"] == 0
    assert value["reviewWireCalls"] == 0
    assert set(value["privateFiles"]) == {"MEMORY.md"}
    assert set(value["publicFiles"]) == {"MEMORY.md"}
    coverage = [attempt for attempt in attempts if attempt.get("usageLedgerId")]
    assert len(coverage) == 1 and coverage[0]["usage"]["cost"] == .004
    assert value["registryReceipt"]["totals"]["cost"] == .004
    assert not value["harnessExists"] and not value["lock"]


def test_concurrent_loaders_all_see_the_sdk_when_it_is_present() -> None:
    # Given the SDK installed, When several judge calls resolve it at the same
    # time, Then every one of them must see it. A cache that stores a flag instead
    # of the in-flight promise reports a false absence to the concurrent callers,
    # which silently turns a configured judge into an unavailable one.
    value = run_bun_script(
        Path(__file__).with_name("sdk-loaded-harness.ts"),
    )
    assert value["results"] == [True] * value["callers"]
    assert value["availableAfter"] is True


def test_an_unavailable_judge_does_not_change_the_memory_outcome() -> None:
    # Given an opted-in judge and an SDK that cannot resolve, When the Memory stage
    # decides, Then it leaves the parent's validated plan to proceed exactly as with
    # Jev off and keeps the reason. Requirements 1 and 3 make the judge optional, so
    # an unavailable judge must not stop learning. A Harness constraint is different:
    # it keeps the conservative hold, so unavailability never releases a constraint.
    value = run_bun_script(Path(__file__).with_name("sdk-absent-decision-harness.ts"), env=ABSENT)
    assert value["memory"] == {"decision": "allow", "reason": "unavailable"}
    assert value["harness"] == {"decision": "propose", "reason": "unavailable"}
