<p align="center">
  <img src="docs/assets/logo.svg" width="88" alt="Incident CodeFix logo">
</p>

<h1 align="center">Incident CodeFix</h1>

<p align="center">
  <b>From GitHub issue to verified pull request, with a human-controlled safety boundary.</b><br>
  Autonomous GitHub incident resolution: sandboxed execution, real evidence, human approval before every GitHub write.
</p>

<p align="center">
  <img alt="TrueFoundry × Polaris — Agents That Act 2026" src="https://img.shields.io/badge/TrueFoundry%20%C3%97%20Polaris-Agents%20That%20Act%202026-8B5CF6?style=flat-square">
  <img alt="Runs on TrueForge" src="https://img.shields.io/badge/runs%20on-TrueForge-22D3EE?style=flat-square">
  <img alt="Sandbox: Daytona" src="https://img.shields.io/badge/sandbox-Daytona-3FB67A?style=flat-square">
  <img alt="Human approval required" src="https://img.shields.io/badge/GitHub%20writes-human%20approval-E5A13A?style=flat-square">
  <img alt="Merge disabled" src="https://img.shields.io/badge/auto--merge-disabled-EF5A5A?style=flat-square">
</p>

<p align="center">
  Built by <b>Abdul Munaf Z</b> · Team <b>Tech Mavericks</b>
</p>

![Human approval: the agent stops before any GitHub change](docs/screenshots/10-human-approval.png)

## What it does

Incident CodeFix takes a real GitHub issue and does the engineering work a reviewer would otherwise redo:

1. **It proves the bug.** The reported command runs in an isolated Daytona workspace, and the failure is
   captured as evidence before any code changes.
2. **It fixes the smallest thing and proves the fix.** A minimal patch plus a regression test, then the
   focused test, the full suite, and a second run in a fresh workspace.
3. **It stops before anything irreversible.** Creating a branch, pushing and opening a PR each wait for a
   human. Merge and deployment are not available at all.

The agent runs on [TrueForge](https://github.com/truefoundry/trueforge), the agent harness: GitHub
access through GitHub MCP, code execution in the sandbox, and approvals through TrueForge's server-side
approval checkpoint. This repository holds the agent: specs, skills, the evidence toolkit, setup scripts,
tests, and the desktop UI prototype.

## The story: issue #2, end to end

> **About these screenshots.** They come from the Incident CodeFix desktop prototype
> ([`prototype/index.html`](prototype/index.html)), which replays a real run on
> [`ABDULMUNAFZ/codefix-demo`](https://github.com/ABDULMUNAFZ/codefix-demo) issue #2. The issue, command,
> traceback, diff (+7 −2), test counts (16 → 17) and commit
> `8c3d5758e9a49fd64bd87586c69331c9319ea4b5` on `codefix/issue-2` are real. Timestamps, durations,
> dashboard metrics, the Daytona workspace name and the sample rows in run history are illustrative. The
> prototype is not connected to GitHub, TrueForge or Daytona.

### 1. GitHub issue

The version compatibility checker raises `InvalidVersion` for a valid prerelease host version.

```bash
python -c "from app.versions import satisfies; print(satisfies('1.5.0-rc1', '>=1.4, <2.0'))"
```

![GitHub issue](docs/screenshots/02-github-issue.png)

### 2. CodeFix receives the issue

The overview shows the active incident, its stage, and recent evidence.

![Overview](docs/screenshots/01-overview.png)

### 3. Repository analysis

The agent reads the issue and the repository through GitHub MCP and detects Python, pip and pytest from
`requirements.txt` and `pytest.ini`. It ranks `app/versions.py` as the likely affected file.

![Agent analysis](docs/screenshots/03-agent-analysis.png)

### 4. Daytona sandbox

The repository is cloned into an isolated workspace and the baseline suite runs: **16 passed**. The
sandbox never receives model or GitHub credentials.

![Daytona sandbox](docs/screenshots/04-daytona-sandbox.png)

### 5. Bug reproduction

The reported command fails exactly as described. The full traceback is kept as evidence:
`satisfies()` → `compare()` → `parse_version()` raises `InvalidVersion: invalid version: '1.5.0-rc1'`
at `app/versions.py:19`.

![Bug reproduction](docs/screenshots/05-bug-reproduction.png)

### 6. Root cause

`_VERSION_RE` accepts only dot-separated numeric releases, so a `-rc1` suffix never matches and the
version is rejected before the requirement is evaluated.

![Root cause](docs/screenshots/06-root-cause.png)

### 7. Minimal patch

One regular expression gains an optional prerelease group; one docstring is updated; one regression
test is added. **2 files, +7 −2**, no dependency or configuration changes.

![Patch](docs/screenshots/07-patch-generation.png)

### 8. Tests

Baseline 16 passed → reproduction 1 failed (expected) → regression 1 passed → full suite
**17 passed, 0 failed** → diff review clean.

![Testing](docs/screenshots/08-testing.png)

### 9. Fresh workspace verification

Clean checkout of the base revision, fresh virtualenv, the exact patch applied, file contents compared
with the tested tree, and the full suite re-run: **17 passed**.

![Fresh workspace verification](docs/screenshots/09-fresh-workspace-verification.png)

### 10. Human approval

The agent stops. Nothing has been written to GitHub. The reviewer sees the root cause, the patch, every
verification result, and the three proposed actions, then approves or rejects.

![Human approval](docs/screenshots/10-human-approval.png)

### 11. Branch creation

After approval, `create_branch` runs: `codefix/issue-2` from `main`.

![Branch creation](docs/screenshots/11-branch-creation.png)

### 12. Push approval

Pushing is its own approval. Only the verified files are pushed, with the approved commit message.

![Push approval](docs/screenshots/12-push-approval.png)

### 13. Pull request approval

Opening the PR is the third approval. There is no merge option.

![PR approval](docs/screenshots/13-pr-approval.png)

### 14. Pull request

PR #3, *Fix #2: Accept prerelease suffixes in compatibility checks*, opens for human review with the
root cause, changes and validation in its description.

![Pull request](docs/screenshots/14-pull-request.png)

### 15. Incident completed

The incident closes with the PR ready for review. Not merged, not deployed.

![Completed](docs/screenshots/15-completed.png)

<details>
<summary><b>More screens:</b> rejection, failure, repositories, run history, incident details, settings</summary>

| Safe stop (reviewer rejects) | Sandbox failure |
| --- | --- |
| ![Safe stop](docs/screenshots/21-safe-stop.png) | ![Failure](docs/screenshots/22-failure.png) |

| Agent repository | Demo repository |
| --- | --- |
| ![codefix-agent](docs/screenshots/16-codefix-agent-repository.png) | ![codefix-demo](docs/screenshots/17-codefix-demo-repository.png) |

| Run history | Incident details |
| --- | --- |
| ![Run history](docs/screenshots/18-run-history.png) | ![Incident details](docs/screenshots/19-incident-details.png) |

| Settings and approval policy |
| --- |
| ![Settings](docs/screenshots/20-settings.png) |

</details>

## Architecture

```
GitHub issue
   │  issue_read · get_file_contents · search_code
   ▼
GitHub MCP ──────────────────────────────┐
   ▼                                     │
TrueForge agent (sessions, approvals)    │  credentials stay in the harness
   ▼                                     │
codefix / incident-codefix skill         │
   ▼                                     │
Daytona sandbox ── repository ── tests ── evidence (exit codes, output)
   ▼
Fresh workspace verification
   ▼
HUMAN APPROVAL  ◀── TrueForge require_approval_for_tools
   ▼
create_branch ─▶ push_files (commit + push) ─▶ create_pull_request ─▶ PR for review (never merged)
```

| Layer | What runs there |
| --- | --- |
| **TrueForge** | The agent loop, model calls, GitHub MCP connector and token, the sandbox tool, and the approval checkpoint. |
| **Skill** | The playbook the agent follows and a stdlib-only toolkit (`cf.py` / `icf.py`) that records every command and refuses to advance without evidence. |
| **Sandbox (Daytona)** | Clone, install, tests, reproduction, patch, fresh-workspace verification. No credentials. |
| **GitHub** | Read through MCP freely; write only through three approval-gated tools. |

## Repository structure

```
codefix-agent/
├── agent/                     TrueForge agent specs and instructions (codefix, incident-codefix)
├── codefix_setup/             Registers connector, skill and agent through the TrueForge API
├── demo/                      Demo issues for codefix-demo
├── skills/
│   ├── codefix/               Issue → verified PR playbook + cf.py evidence toolkit
│   └── incident-codefix/      Multi-stack playbook (Python, JS/TS, Go, Rust, Java) + icf.py
├── incident_service/          Webhook intake, incident store and approval bridge (see docs)
├── prototype/                 Desktop UI prototype (static HTML, demo data)
├── docs/                      Incident CodeFix design doc, screenshots, logo
├── tests/                     Unit, workflow and service tests
├── .env.example               CodeFix configuration template
├── package.json               npm scripts
├── pyproject.toml             ruff · mypy · pytest configuration
└── requirements-dev.txt
```

## Setup

Requirements: Node ≥ 22, Python ≥ 3.10, git, a model API key, and a GitHub fine-grained PAT.

```bash
# 1. Harness
npx @truefoundry/trueforge            # UI + API on http://localhost:8790
#    In the UI: Settings → Model providers → add your provider.
#    Settings → Sandbox providers → Daytona (otherwise TrueForge's local sandbox is used).

# 2. CodeFix
git clone https://github.com/ABDULMUNAFZ/codefix-agent && cd codefix-agent
npm run bootstrap                     # .venv with pytest/ruff/mypy
cp .env.example .env                  # fill in CODEFIX_MODEL and GITHUB_PAT
npm run setup                         # registers GitHub MCP, skill, agent
npm run check                         # lint + typecheck + tests
```

**GitHub PAT:** go to Settings → Developer settings → Fine-grained tokens. Choose **Only select
repositories** and pick the target repo. Set Contents read/write, Pull requests read/write, Issues read,
Metadata read, and a short expiry. The token goes into TrueForge's connector store; it is never written
to this repository or the sandbox.

| Variable | Required | Purpose |
| --- | --- | --- |
| `TRUEFORGE_URL` | no (`http://localhost:8790`) | TrueForge API |
| `TRUEFORGE_API_TOKEN` | only with auth enabled | Bearer token for the TrueForge API |
| `CODEFIX_MODEL` | yes | Model FQN from `GET /api/v1/models` |
| `CODEFIX_TARGET_REPO` | yes | The one repo CodeFix may touch |
| `CODEFIX_SKILL_REPO_URL` / `CODEFIX_SKILL_REF` | yes / `main` | Where TrueForge clones the skill from (must be a public GitHub repo) |
| `CODEFIX_GITHUB_MCP_NAME` | no (`github`) | Connector name in TrueForge |
| `GITHUB_PAT` | first run | Handed to TrueForge's connector store; leave empty to keep the stored token |

Incident CodeFix (the multi-repo workflow) uses its own connector `github-incident` and its own
`.env.incident`; see [`docs/incident-codefix.md`](docs/incident-codefix.md).

## Usage

**Run the agent.** In the TrueForge UI, choose the `codefix` agent and send:

```
Fix https://github.com/ABDULMUNAFZ/codefix-demo/issues/2
```

Or run `npm run demo -- 2` to start the session through the API, then follow the trace and answer the
approval cards in the TrueForge UI.

**Open the desktop prototype.** Open [`prototype/index.html`](prototype/index.html) in a browser. It is a
static, clickable walkthrough of the workflow (Overview → Incident → … → Pull Request, plus the reject and
failure paths). It needs no server and makes no network calls apart from loading fonts.

## Approval model

| Action | Policy | How it is enforced |
| --- | --- | --- |
| Read issue, code, tests | automatic | read-only GitHub MCP tools |
| Sandbox execution, install, tests, reproduction, patch, verification | automatic | inside the sandbox only |
| Create branch | **human approval** | TrueForge `require_approval_for_tools` |
| Push files (commit + push) | **human approval** | TrueForge `require_approval_for_tools` |
| Create pull request | **human approval** | TrueForge `require_approval_for_tools` |
| Merge | disabled | tool not enabled; setup rejects specs that enable it |
| Deployment | disabled | no such tool |

Approval is enforced by TrueForge's server, not by the prompt. When the agent calls a gated tool, TrueForge
pauses the turn and waits for an explicit allow or deny. A denial stops the run with no further writes.

## Security

- **Sandboxed execution.** Repository code runs only in the Daytona (or local) sandbox.
- **No credentials in the sandbox or the repository.** Model and GitHub tokens live in TrueForge's
  connector store and are never printed (tests check this).
- **Least privilege.** An explicit tool allowlist, a fine-grained token scoped to the target repo, and an
  allowed-repository check in both the instructions and the toolkit.
- **Untrusted input stays data.** Issue text, repository content and tool output are never treated as
  instructions; instruction-like text is flagged in the report.
- **No fabricated results.** Every PASS or FAIL comes from a recorded command with its exit code, and the
  phase gates refuse to advance without it.
- **No automatic merge, no automatic deployment.**

## Failure handling

| Condition | Result |
| --- | --- |
| Issue not reproduced | Stops before patching; reports commands, output and environment |
| Patch does not fix the bug, or a regression appears | Stops; nothing is pushed |
| Sandbox, clone or install failure | Stops with the actual error; no GitHub change |
| Human rejects | Safe stop; investigation preserved; no branch, push or PR |
| GitHub API error | Stops and reports the exact error |
| Pushed files differ from the tested files | Stops; never reported as verified |

## Known limitations

- Fresh workspace verification uses a new directory and virtualenv inside the **same** session sandbox,
  not a newly provisioned sandbox.
- `push_files` cannot delete or rename files, so patches that need either are refused.
- The `codefix` skill supports Python with pip and pytest; `incident-codefix` adds JS/TS, Go, Rust and
  Java detection. Non-Python installs need Daytona, because TrueForge's local sandbox only allows GitHub
  and PyPI traffic.
- The desktop UI is a prototype with demo data. It is not yet wired to the live agent.

## AI-assisted development disclosure

AI-assisted development was used during implementation for code generation, debugging assistance and
documentation. Specifically, **Claude Code** (Anthropic) was used to read the TrueForge source and API,
write code, tests, the desktop prototype and documentation, and validate the agent specs against
TrueForge's schema.

The team understands and can explain the architecture, sandbox execution, agent workflow, approval model
and safety boundaries.

<img width="1766" height="915" alt="Screenshot 2026-09-26 at 4 26 12 PM" src="https://github.com/user-attachments/assets/88c28f71-7719-441e-bd3c-010361450c5c" />


## Hackathon and team

| | |
| --- | --- |
| **Hackathon** | TrueFoundry × Polaris — Agents That Act 2026 |
| **Product** | Incident CodeFix |
| **Builder** | Abdul Munaf Z |
| **Team** | Tech Mavericks |
| **Harness** | [TrueForge](https://github.com/truefoundry/trueforge) |
| **Target repository** | [ABDULMUNAFZ/codefix-demo](https://github.com/ABDULMUNAFZ/codefix-demo) |



