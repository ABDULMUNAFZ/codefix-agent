import copy

import pytest

from codefix_setup.config import Settings, check_agent_policy, render_agent

SETTINGS = Settings(
    trueforge_url="http://localhost:8790",
    trueforge_api_token=None,
    model="anthropic/claude-sonnet-5",
    target_repo="acme/codefix-demo",
    github_mcp_name="github",
    github_pat=None,
    skill_repo_url="https://github.com/acme/codefix-agent",
    skill_ref="main",
)


@pytest.fixture
def agent():
    return render_agent(SETTINGS)


def _github(agent):
    return agent["manifest"]["mcp_servers"][0]


def test_rendered_agent_satisfies_policy(agent):
    assert check_agent_policy(agent, "github") == []
    assert "{{" not in str(agent)
    assert "acme/codefix-demo" in agent["manifest"]["instructions"]
    assert agent["manifest"]["model"]["name"] == "anthropic/claude-sonnet-5"


def test_every_github_write_requires_approval(agent):
    approval = set(_github(agent)["require_approval_for_tools"])
    assert {"create_branch", "push_files", "create_pull_request", "@write", "@destructive"} <= approval


@pytest.mark.parametrize("tool", ["create_branch", "push_files", "create_pull_request"])
def test_policy_rejects_write_without_approval(agent, tool):
    broken = copy.deepcopy(agent)
    approval = _github(broken)["require_approval_for_tools"]
    approval.remove(tool)
    approval.remove("@write")
    assert f"{tool} must require approval" in check_agent_policy(broken, "github")


@pytest.mark.parametrize("tool", ["merge_pull_request", "delete_file", "create_repository"])
def test_policy_rejects_dangerous_tools(agent, tool):
    broken = copy.deepcopy(agent)
    _github(broken)["enable_tools"].append(tool)
    assert f"{tool} must not be enabled" in check_agent_policy(broken, "github")


def test_policy_rejects_tag_allowlist_and_missing_sandbox(agent):
    broken = copy.deepcopy(agent)
    _github(broken)["enable_tools"] = ["@all"]
    broken["manifest"]["config"]["sandbox"]["enabled"] = False
    broken["manifest"]["config"]["dynamic_sub_agents"]["enabled"] = True
    problems = check_agent_policy(broken, "github")
    assert "GitHub tools must be an explicit allowlist, not a tag" in problems
    assert "sandbox must be enabled" in problems
    assert "dynamic sub-agents must be disabled" in problems


def test_no_secrets_in_agent_or_skill(agent):
    from codefix_setup.config import ROOT

    text = str(agent) + (ROOT / "skills" / "codefix" / "SKILL.md").read_text()
    for marker in ("ghp_", "github_pat_", "sk-ant-", "Bearer "):
        assert marker not in text
