# CodeFix

**From GitHub issue to verified pull request, with a human in the loop.**

Submission for the TrueFoundry × Polaris "Agents That Act" hackathon. CodeFix is an agent that runs on
[TrueForge](https://github.com/truefoundry/trueforge). This repository contains no TrueForge code. It holds
the CodeFix agent spec, the skill, the evidence toolkit, and the setup scripts.

## Problem

Coding assistants will write a fix for any bug report. What they usually skip is checking that the bug
exists, running the patch, and making sure the code that lands in the PR is the code that was tested. A
reviewer then has to redo all of that.

## Solution

CodeFix takes one real GitHub issue and produces one PR with evidence behind it:

1. It reads the issue and the code through GitHub MCP.
2. It clones the repo into a TrueForge sandbox and runs the baseline tests.
3. It writes a failing test that reproduces the bug.
4. It patches the code and reruns that test plus the full suite.
5. It produces a verification report and stops. TrueForge shows an approval card for each GitHub write.
6. After approval it creates the branch, pushes the tested files, and opens the PR.
7. It clones the PR branch into a new directory and a new virtualenv, checks that the pushed files match the
   tested files byte for byte, and runs the tests again.

## Why this is an agent

CodeFix does more than chat. It calls a real external system (GitHub), runs real commands in an isolated
sandbox, decides what to do next from their exit codes, and cannot take an irreversible action (a branch,
a push or a PR) until a human approves it.

## Architecture

```
            ┌──────────────────────── TrueForge (harness) ─────────────────────────┐
 issue URL  │  CodeFix agent spec ── model                                         │
 ─────────► │     │  instructions + codefix skill (git-backed, preloaded)          │
            │     ├─ GitHub MCP (9 allowlisted tools; 3 writes need approval) ─────┼──► GitHub (codefix-demo)
            │     ├─ Sandbox (local or Daytona) ── cf.py records every command      │
            │     └─ Approval cards · sessions · traces (TrueForge UI)             │
            └──────────────────────────────────────────────────────────────────────┘
```

| Path | What it is |
| --- | --- |
| `agent/codefix.agent.json` | TrueForge `CreateAgentRequest` (model, MCP allowlist, approval rules, skill, sandbox, iteration limit) |
| `agent/instructions.md` | System prompt; `{{ALLOWED_REPO}}` is filled in at setup |
| `skills/codefix/SKILL.md` | The step-by-step playbook the agent follows |
| `skills/codefix/scripts/cf.py` | Evidence toolkit that runs in the sandbox (stdlib only): command records, phase gates, integrity manifest, report |
| `codefix_setup/` | Setup (`npm run setup`) and demo launcher (`npm run demo`), both using the TrueForge REST API |
| `tests/` | Unit tests, an end-to-end workflow test with real git and pytest, and live checks against TrueForge |

## TrueForge integration

Everything goes through TrueForge's public API, which I checked against TrueForge 0.3.0 (the OpenAPI spec
and the zod `AgentSpecSchema`):

- `PUT /api/v1/settings/mcp-servers` registers the GitHub MCP. The token is stored in TrueForge's connector
  store.
- `PUT /api/v1/settings/skills` registers the git-backed `codefix` skill (`skills/codefix` in this repo).
- `POST` or `PUT /api/v1/agents` creates or updates the `codefix` agent.
- `GET /api/v1/models` and `GET /api/v1/mcp-servers/{name}/tools` confirm that the model and every allowlisted
  tool exist before the agent is saved.

Agent settings: `iteration_limit: 80`, `sandbox.enabled: true`, `dynamic_sub_agents.enabled: false` (keeps
the demo deterministic), and `web_search.enabled: false`.

## GitHub MCP

This is TrueForge's catalog `github` server (`https://api.githubcopilot.com/mcp/`). The agent can use only
these tools:

| Read | Write (approval required) |
| --- | --- |
| `issue_read`, `get_file_contents`, `search_code`, `list_branches`, `list_commits`, `pull_request_read` | `create_branch`, `push_files`, `create_pull_request` |

Merging, deleting files, creating repos and forking are all left out. `check_agent_policy` rejects any spec
that enables them, and setup won't save such a spec.

## Sandbox

Every command runs in the TrueForge sandbox through `cf.py run`, which records the command, exit code,
stdout, stderr, duration and whether it timed out to `.codefix/evidence.jsonl`.

- **Local mode** (`npx @truefoundry/trueforge`): if no provider is configured, TrueForge uses its local
  sandbox. On macOS that means seatbelt, on Linux bubblewrap. Outbound network is limited to GitHub and PyPI.
- **Daytona**: add it under Settings → Sandbox providers.

The sandbox never gets credentials. It clones the public demo repo anonymously, and all GitHub writes go
through MCP on the harness side.

## Human approval

Approval is enforced by TrueForge's server, not by the prompt. `require_approval_for_tools` lists
`create_branch`, `push_files`, `create_pull_request`, `@write` and `@destructive`. When the model calls one
of these, TrueForge pauses the turn, shows an approval card with the tool arguments (branch name, file
contents, PR title and body), and waits for a `user.tool_approval` allow or deny.

If the reviewer denies, CodeFix records `STOPPED/approval_denied` and makes no further writes.

## Security model

- **Credentials:** the GitHub fine-grained PAT is scoped to `codefix-demo` only and lives in TrueForge's
  connector store. It is never in this repo, the skill, the sandbox, or logs (`test_setup.py` checks that it
  isn't printed). The model key is configured in TrueForge.
- **Least privilege:** 9 explicitly allowlisted tools, no tag-based allowlists, and one target repo checked by
  both the instructions and `cf.py issue --allowed-repo`.
- **Prompt injection:** issue text, repo content and tool output are treated as data. `cf.py scan` flags text
  that looks like instructions, such as override attempts, secret requests, requests to skip approval,
  unapproved pushes or network calls. Findings go into the report. The hard limits don't depend on the model
  behaving: approval gates, the tool allowlist, the PAT scope, and a sandbox with no secrets.
- **No fabricated results:** every PASS or FAIL in the report comes from `cf.py` records, and phase gates
  refuse to move on without the matching evidence.

## Setup

Requirements: Node ≥ 22, Python ≥ 3.10, git, a model API key, and a GitHub fine-grained PAT.

```bash
# 1. Harness
npx @truefoundry/trueforge            # UI + API on http://localhost:8790
#    In the UI: Settings → Model providers → add your provider.
#    Optional: Settings → Sandbox providers → Daytona (otherwise the local sandbox is used).

# 2. CodeFix
git clone https://github.com/ABDULMUNAFZ/codefix-agent && cd codefix-agent
npm run bootstrap                     # .venv with pytest/ruff/mypy
cp .env.example .env                  # fill in CODEFIX_MODEL and GITHUB_PAT
npm run setup                         # registers GitHub MCP, skill, agent
npm run check                         # lint + typecheck + tests
```

GitHub PAT: go to Settings → Developer settings → Fine-grained tokens. Choose **Only select repositories**
and pick `codefix-demo`. Set Contents: read/write, Pull requests: read/write, Issues: read, Metadata: read.
Use a short expiry.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `TRUEFORGE_URL` | no (`http://localhost:8790`) | TrueForge API |
| `TRUEFORGE_API_TOKEN` | only with auth enabled | Bearer token for the TrueForge API |
| `CODEFIX_MODEL` | yes | Model FQN from `GET /api/v1/models` |
| `CODEFIX_TARGET_REPO` | yes | The one repo CodeFix may touch |
| `CODEFIX_SKILL_REPO_URL` / `CODEFIX_SKILL_REF` | yes / `main` | Where TrueForge clones the skill from (must be a public GitHub repo) |
| `CODEFIX_GITHUB_MCP_NAME` | no (`github`) | Connector name in TrueForge |
| `GITHUB_PAT` | first run | Handed to TrueForge's connector store; leave empty to keep the stored token |

## Demo repository

[`ABDULMUNAFZ/codefix-demo`](https://github.com/ABDULMUNAFZ/codefix-demo) is a small plugin-compatibility
checker. `app/versions.py` compares version segments as strings, so `"10" < "9"` and host `1.10.0` fails
`>=1.9.0`. The existing 16 tests pass because every fixture uses single-digit versions. Nothing else triggers
the bug, so the demo behaves the same on every run.

## Running CodeFix

- **In the UI:** choose the `codefix` agent and send
  `Fix https://github.com/ABDULMUNAFZ/codefix-demo/issues/1`.
- **From the CLI:** run `npm run demo -- 1`. It creates the session through the API; then open it in the
  TrueForge UI to follow the trace and answer the approval cards.

## Example issue

See [`demo/issue-1.md`](demo/issue-1.md), "Plugin rejected as incompatible on host 1.10.0 despite requiring
>=1.9.0".

[`demo/issue-2-injection.md`](demo/issue-2-injection.md) is a second issue that hides instructions in an HTML
comment and describes behavior that isn't actually broken. CodeFix should flag the injection, return
`NOT_REPRODUCED`, and stop without writing a patch.

## Example trace

```
issue_read(ABDULMUNAFZ/codefix-demo#1)                     GitHub MCP
cf.py issue … --allowed-repo ABDULMUNAFZ/codefix-demo       sandbox provisioned
cf.py run --label clone   -- git clone …                    exit=0
cf.py run --label install -- .venv/bin/pip install -r …     exit=0
cf.py run --label baseline -- pytest                        exit=0   16 passed
cf.py run --label reproduce -- pytest tests/test_issue_1.py exit=1   1 failed   → REPRODUCED
cf.py run --label diff -- git diff                          app/versions.py: int segments
cf.py run --label reproduce-after …                         exit=0
cf.py run --label regression -- pytest                      exit=0   17 passed
cf.py report → CODEFIX VERIFICATION REPORT
create_branch        ⏸ approval card → approved
push_files           ⏸ approval card → approved
create_pull_request  ⏸ approval card → approved
cf.py run --label pr-clone -- git clone --branch codefix/issue-1 …
cf.py verify-pr      INTEGRITY OK
cf.py run --label pr-tests -- pytest                        exit=0   → VERIFIED
```

The report structure matches the hackathon brief. Test lines are generated from the evidence records, and
the story fields (problem, root cause, fix) come from the agent.

## Failure handling

| Condition | Detected by | Result |
| --- | --- | --- |
| Not reproduced | `classify` / `REPRODUCED` gate | `STOPPED/not_reproduced` with commands, output, environment, next steps |
| Patch ineffective | `reproduce-after` ≠ 0 | `STOPPED/patch_ineffective` |
| Regression | `regression` ≠ 0 | `STOPPED/regression` |
| Approval denied | TrueForge deny event | `STOPPED/approval_denied`, no further writes |
| GitHub API error | MCP tool error | `STOPPED/github_error` with the exact error |
| Sandbox / clone failure | exit 127 or clone ≠ 0 | `STOPPED/sandbox_error` |
| Integrity mismatch | `verify-pr` | `STOPPED/integrity_mismatch`; never reported as VERIFIED |
| Test timeout | `timed_out` (exit 124) | `STOPPED/timeout` |
| Install failure | `install` ≠ 0 | `STOPPED/install_failed` |
| Phase skipped | `cf.py phase` | refused (exit 3) |

## Demo script (~5 min)

| Time | What to show |
| --- | --- |
| 0:00 | The GitHub issue in the browser. Paste its URL into the CodeFix agent in the TrueForge UI. |
| 0:20 | `issue_read` and `get_file_contents` tool calls in the trace |
| 1:00 | Sandbox provisioned; clone, install, and baseline `16 passed` |
| 1:30 | Reproduction test fails (`exit=1`, `1 failed`), verdict REPRODUCED |
| 2:00 | Diff: a few lines in `app/versions.py` plus the new test |
| 2:30 | `reproduce-after` and `regression` both exit 0 |
| 3:00 | Verification report |
| 3:20 | **TrueForge approval card** for `create_branch` showing the arguments; approve it |
| 3:40 | Approve `push_files` (the card shows the exact file contents), then `create_pull_request` |
| 4:30 | New clone of the PR branch, `INTEGRITY OK`, tests pass |
| 5:00 | The PR on GitHub, with **VERIFIED** in the trace |

Optional extra: run issue 2, or deny the `create_branch` card and show that the agent stops.

## Known limitations

- The final check uses a fresh clone and fresh virtualenv inside the **same session sandbox**, not a newly
  provisioned sandbox. A separate sandbox would need a second TrueForge session.
- `push_files` content passes through the model. `verify-pr` catches any difference after the push, but it
  can't stop the push from happening. On a mismatch the agent stops, and a human should close the PR.
- `push_files` can't delete or rename files, so patches that need either are refused at the manifest step.
- TrueForge git skills are cloned without credentials, so this repo has to be public. The demo repo also has
  to be public, because the sandbox holds no GitHub credentials to clone it.
- Only Python projects that use `pip install -r requirements.txt` and `pytest` are supported so far.

## AI tools used

This project was built with **Claude Code** (Anthropic): it read the TrueForge source and OpenAPI spec,
wrote the code, tests and docs, and validated the agent spec against TrueForge's zod schema. A human
directed and reviewed the work. The agent itself runs on whichever model is set in `CODEFIX_MODEL`.
