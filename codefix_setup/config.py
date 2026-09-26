"""Environment-driven settings and agent-spec rendering for CodeFix setup."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AGENT_TEMPLATE = ROOT / "agent" / "codefix.agent.json"
INSTRUCTIONS = ROOT / "agent" / "instructions.md"

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"
WRITE_TOOLS = ("create_branch", "push_files", "create_pull_request")

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class Settings:
    trueforge_url: str
    trueforge_api_token: str | None
    model: str
    target_repo: str
    github_mcp_name: str
    github_pat: str | None
    skill_repo_url: str
    skill_ref: str


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines without overriding variables already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required setting {name} (see .env.example)")
    return value


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    target = _required("CODEFIX_TARGET_REPO")
    if not _REPO_RE.match(target):
        raise SystemExit("CODEFIX_TARGET_REPO must look like owner/repo")
    return Settings(
        trueforge_url=os.environ.get("TRUEFORGE_URL", "http://localhost:8790"),
        trueforge_api_token=os.environ.get("TRUEFORGE_API_TOKEN") or None,
        model=_required("CODEFIX_MODEL"),
        target_repo=target,
        github_mcp_name=os.environ.get("CODEFIX_GITHUB_MCP_NAME", "github"),
        github_pat=os.environ.get("GITHUB_PAT") or None,
        skill_repo_url=_required("CODEFIX_SKILL_REPO_URL"),
        skill_ref=os.environ.get("CODEFIX_SKILL_REF", "main"),
    )


def _substitute(node: Any, values: dict[str, str]) -> Any:
    if isinstance(node, str):
        for key, value in values.items():
            node = node.replace("{{" + key + "}}", value)
        return node
    if isinstance(node, list):
        return [_substitute(item, values) for item in node]
    if isinstance(node, dict):
        return {key: _substitute(item, values) for key, item in node.items()}
    return node


def render_agent(settings: Settings) -> dict[str, Any]:
    """Return the CreateAgentRequest body for the CodeFix agent."""
    instructions = INSTRUCTIONS.read_text().replace("{{ALLOWED_REPO}}", settings.target_repo)
    template = json.loads(AGENT_TEMPLATE.read_text())
    rendered: dict[str, Any] = _substitute(
        template,
        {
            "CODEFIX_MODEL": settings.model,
            "GITHUB_MCP_NAME": settings.github_mcp_name,
            "INSTRUCTIONS": instructions,
        },
    )
    return rendered


def check_agent_policy(agent: dict[str, Any], github_mcp_name: str) -> list[str]:
    """Least-privilege and approval invariants the demo depends on."""
    problems: list[str] = []
    manifest = agent["manifest"]
    servers = [s for s in manifest.get("mcp_servers", []) if s["name"] == github_mcp_name]
    if len(servers) != 1:
        return [f"agent must attach exactly one '{github_mcp_name}' MCP server"]
    server = servers[0]
    enabled = server.get("enable_tools", ["@all"])
    if any(selector.startswith("@") for selector in enabled):
        problems.append("GitHub tools must be an explicit allowlist, not a tag")
    approval = set(server.get("require_approval_for_tools", []))
    for tool in WRITE_TOOLS:
        if tool not in approval:
            problems.append(f"{tool} must require approval")
        if tool not in enabled:
            problems.append(f"{tool} must be enabled")
    for forbidden in ("merge_pull_request", "delete_file", "create_or_update_file", "create_repository", "fork_repository"):
        if forbidden in enabled:
            problems.append(f"{forbidden} must not be enabled")
    config = manifest.get("config", {})
    if not config.get("sandbox", {}).get("enabled"):
        problems.append("sandbox must be enabled")
    if config.get("dynamic_sub_agents", {}).get("enabled", True):
        problems.append("dynamic sub-agents must be disabled")
    if not any(skill["name"] == "codefix" for skill in manifest.get("skills", [])):
        problems.append("codefix skill must be attached")
    return problems
