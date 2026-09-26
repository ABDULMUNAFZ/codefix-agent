"""Start a CodeFix session for one issue; watch and approve it in the TrueForge UI.

Usage: python -m codefix_setup.demo <issue-number>
"""

from __future__ import annotations

import sys

from codefix_setup.config import load_settings
from codefix_setup.trueforge import TrueForgeClient, TrueForgeError


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    settings = load_settings()
    client = TrueForgeClient(base_url=settings.trueforge_url, api_token=settings.trueforge_api_token)
    issue_url = f"https://github.com/{settings.target_repo}/issues/{argv[0]}"
    try:
        session = client.post(
            "/api/v1/sessions",
            {"agent": {"name": "codefix"}, "metadata": {"codefix_issue": issue_url}},
        )["data"]
        turn = client.post(
            f"/api/v1/sessions/{session['id']}/turns",
            {"input": [{"type": "user.message", "content": f"Fix {issue_url}"}], "stream": False},
        )["data"]
    except TrueForgeError as exc:
        print(f"TrueForge API error: {exc}", file=sys.stderr)
        return 1
    print(f"Session {session['id']} started (turn {turn['id']}, state {turn['state']}).")
    print(f"Open {settings.trueforge_url} → Sessions to follow the trace and answer approval cards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
