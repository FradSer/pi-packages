from test_skill_router import installed_collection, source_repo, run_harness


def test_routing_appends_guidelines_and_ignores_custom_runs(installed_collection) -> None:
    """Given installed routes, When runs start, Then only user matches add a guideline."""
    agent_dir = installed_collection["agent_dir"]
    user = run_harness(agent_dir, "route", "please diagnose this bug")
    assert user["ok"], user
    assert user["promptGuidelines"][0] == "existing guideline"
    assert user["promptGuidelines"] == ["existing guideline"]
    assert user["sections"]["other"] == "retained"
    assert "bug-diagnosis" in user["sections"]["skill_router"]
    custom = run_harness(agent_dir, "route-custom")
    assert custom["ok"], custom
    assert custom["promptGuidelines"] == ["existing guideline"]
    assert custom["message"] is None
