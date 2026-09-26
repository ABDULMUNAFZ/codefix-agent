"""Checks against a running TrueForge after `npm run setup`. Skipped unless CODEFIX_LIVE=1."""

import os

import pytest

from codefix_setup.config import WRITE_TOOLS, check_agent_policy, load_settings
from codefix_setup.trueforge import TrueForgeClient

pytestmark = pytest.mark.skipif(os.environ.get("CODEFIX_LIVE") != "1", reason="set CODEFIX_LIVE=1 with TrueForge running")


@pytest.fixture(scope="module")
def ctx():
    settings = load_settings()
    return settings, TrueForgeClient(base_url=settings.trueforge_url, api_token=settings.trueforge_api_token)


def test_server_side_agent_keeps_approval_policy(ctx):
    settings, client = ctx
    agents = client.get("/api/v1/agents?agent_name=codefix")["data"]
    agent = next(a for a in agents if a["name"] == "codefix")
    assert check_agent_policy(agent, settings.github_mcp_name) == []


def test_github_mcp_is_authenticated_and_exposes_write_tools(ctx):
    settings, client = ctx
    server = client.get(f"/api/v1/settings/mcp-servers/{settings.github_mcp_name}")["data"]
    assert server["auth_status"]["status"] in {"authenticated", "not_required"}
    assert "Bearer ghp_" not in str(server) and "github_pat_" not in str(server)
    tools = {t["name"] for t in client.get(f"/api/v1/mcp-servers/{settings.github_mcp_name}/tools")["data"]}
    assert set(WRITE_TOOLS) <= tools


def test_codefix_skill_registered(ctx):
    _, client = ctx
    skills = client.get("/api/v1/settings/skills")["data"]
    assert any(s["name"] == "codefix" for s in skills)
