import pytest

from codefix_setup import setup
from codefix_setup.config import Settings
from codefix_setup.trueforge import TrueForgeError


class FakeClient:
    def __init__(self, *, models=(), mcp_exists=True, tools=(), agents=()):
        self.models, self.mcp_exists, self.tools, self.agents = list(models), mcp_exists, list(tools), list(agents)
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path, None))
        if path == "/api/v1/models":
            return {"data": [{"name": m} for m in self.models]}
        if path.startswith("/api/v1/settings/mcp-servers/"):
            if not self.mcp_exists:
                raise TrueForgeError(method="GET", path=path, status=404, body="not found")
            return {"data": {}}
        if path.endswith("/tools"):
            return {"data": [{"name": t} for t in self.tools]}
        if path.startswith("/api/v1/agents"):
            return {"data": self.agents}
        raise AssertionError(path)

    def put(self, path, body):
        self.calls.append(("PUT", path, body))

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        return {"data": {"id": "agent-1"}}


def settings(pat=None):
    return Settings("http://x", None, "anthropic/m", "acme/demo", "github", pat, "https://github.com/acme/codefix-agent", "main")


def test_missing_model_fails_fast():
    with pytest.raises(SystemExit, match="not configured"):
        setup.ensure_model(FakeClient(models=["openai/x"]), "anthropic/m")


def test_github_token_goes_to_trueforge_and_is_never_printed(capsys):
    client = FakeClient(mcp_exists=False)
    setup.ensure_github_mcp(client, settings(pat="ghp_secretvalue"))
    method, path, body = client.calls[-1]
    assert (method, path) == ("PUT", "/api/v1/settings/mcp-servers")
    assert body["manifest"]["auth"]["headers"]["Authorization"] == "Bearer ghp_secretvalue"
    assert "ghp_secretvalue" not in capsys.readouterr().out


def test_missing_github_connector_without_token_fails():
    with pytest.raises(SystemExit, match="not configured"):
        setup.ensure_github_mcp(FakeClient(mcp_exists=False), settings())


def test_allowlisted_tool_missing_from_server_fails():
    agent = {"manifest": {"mcp_servers": [{"name": "github", "enable_tools": ["issue_read", "push_files"]}]}}
    with pytest.raises(SystemExit, match="push_files"):
        setup.check_github_tools(FakeClient(tools=["issue_read"]), settings(), agent)


def test_agent_is_created_then_updated():
    agent = {"name": "codefix", "description": "d", "manifest": {}}
    client = FakeClient()
    setup.ensure_agent(client, agent)
    assert client.calls[-1][0:2] == ("POST", "/api/v1/agents")
    client = FakeClient(agents=[{"name": "codefix", "id": "agent-9"}])
    setup.ensure_agent(client, agent)
    assert client.calls[-1][0:2] == ("PUT", "/api/v1/agents/agent-9")
