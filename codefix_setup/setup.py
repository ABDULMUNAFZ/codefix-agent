"""Register the GitHub MCP server, the CodeFix skill, and the CodeFix agent in TrueForge.

Idempotent: safe to re-run after changing the agent spec, skill ref, or token.
"""

from __future__ import annotations

import sys
from typing import Any

from codefix_setup.config import (
    GITHUB_MCP_URL,
    Settings,
    check_agent_policy,
    load_settings,
    render_agent,
)
from codefix_setup.trueforge import TrueForgeClient, TrueForgeError


def ensure_model(client: TrueForgeClient, model: str) -> None:
    names = [m["name"] for m in client.get("/api/v1/models")["data"]]
    if model not in names:
        listed = ", ".join(names) or "none — add a model provider under Settings"
        raise SystemExit(f"model {model!r} is not configured in TrueForge (available: {listed})")


def ensure_github_mcp(client: TrueForgeClient, settings: Settings) -> None:
    name = settings.github_mcp_name
    try:
        client.get(f"/api/v1/settings/mcp-servers/{name}")
        exists = True
    except TrueForgeError as exc:
        if exc.status != 404:
            raise
        exists = False
    if settings.github_pat is None:
        if not exists:
            raise SystemExit(f"MCP server '{name}' is not configured; set GITHUB_PAT or add it under Settings → Connectors")
        print(f"• GitHub MCP '{name}': already configured (token untouched)")
        return
    manifest = {
        "type": "remote",
        "name": name,
        "url": GITHUB_MCP_URL,
        "description": "GitHub issues, repository files, branches, and pull requests for the CodeFix target repository.",
        "auth": {"type": "header", "headers": {"Authorization": f"Bearer {settings.github_pat}"}},
    }
    client.put("/api/v1/settings/mcp-servers", {"manifest": manifest})
    print(f"• GitHub MCP '{name}': {'updated' if exists else 'created'} (token stored in TrueForge, not printed)")


def check_github_tools(client: TrueForgeClient, settings: Settings, agent: dict[str, Any]) -> None:
    tools = {t["name"] for t in client.get(f"/api/v1/mcp-servers/{settings.github_mcp_name}/tools")["data"]}
    server = next(s for s in agent["manifest"]["mcp_servers"] if s["name"] == settings.github_mcp_name)
    missing = [tool for tool in server["enable_tools"] if tool not in tools]
    if missing:
        raise SystemExit(f"GitHub MCP does not expose: {', '.join(missing)}. Update agent/codefix.agent.json.")
    print(f"• GitHub MCP exposes all {len(server['enable_tools'])} allowlisted tools")


def ensure_skill(client: TrueForgeClient, settings: Settings) -> None:
    manifest = {
        "type": "git",
        "name": "codefix",
        "url": settings.skill_repo_url,
        "path": "skills/codefix",
        "ref": settings.skill_ref,
        "description": (
            "Reproduce a GitHub bug in the sandbox, apply a minimal tested patch, report evidence, "
            "open a PR after approval, and re-verify it."
        ),
    }
    client.put("/api/v1/settings/skills", {"manifest": manifest})
    print(f"• Skill 'codefix': {settings.skill_repo_url}@{settings.skill_ref}")


def ensure_agent(client: TrueForgeClient, agent: dict[str, Any]) -> str:
    listing = client.get(f"/api/v1/agents?agent_name={agent['name']}")["data"]
    existing = next((a for a in listing if a["name"] == agent["name"]), None)
    if existing is None:
        created = client.post("/api/v1/agents", agent)["data"]
        print(f"• Agent '{agent['name']}': created ({created['id']})")
        return str(created["id"])
    client.put(
        f"/api/v1/agents/{existing['id']}",
        {"description": agent["description"], "manifest": agent["manifest"]},
    )
    print(f"• Agent '{agent['name']}': updated ({existing['id']})")
    return str(existing["id"])


def main() -> int:
    settings = load_settings()
    agent = render_agent(settings)
    problems = check_agent_policy(agent, settings.github_mcp_name)
    if problems:
        print("Agent spec violates CodeFix policy:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    client = TrueForgeClient(base_url=settings.trueforge_url, api_token=settings.trueforge_api_token)
    try:
        ensure_model(client, settings.model)
        ensure_github_mcp(client, settings)
        check_github_tools(client, settings, agent)
        ensure_skill(client, settings)
        ensure_agent(client, agent)
    except TrueForgeError as exc:
        print(f"TrueForge API error: {exc}", file=sys.stderr)
        return 1
    print(f"\nReady. Open {settings.trueforge_url}, choose agent 'codefix', and send:\n")
    print(f"  Fix https://github.com/{settings.target_repo}/issues/<number>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
