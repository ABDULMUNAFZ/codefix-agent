#!/usr/bin/env python3
"""CodeFix evidence toolkit. Runs inside the TrueForge sandbox; standard library only.

The model never reports a test result itself: every PASS/FAIL in the final report
is derived from command records written by `cf.py run`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("CODEFIX_STATE_DIR", ".codefix"))
OUTPUT_LIMIT = 8000
DEFAULT_TIMEOUT = 300

EXIT_GATE = 3
EXIT_INTEGRITY = 4
EXIT_NOT_ALLOWED = 5

# Linear happy path; STOPPED is reachable from any non-terminal phase.
PHASES = [
    "INIT",
    "CLONED",
    "INSTALLED",
    "BASELINE",
    "REPRODUCED",
    "PATCHED",
    "VERIFIED_LOCAL",
    "AWAITING_APPROVAL",
    "PUSHED",
    "PR_OPEN",
    "PR_VERIFIED",
]
TERMINAL = {"PR_VERIFIED", "STOPPED"}

STOP_REASONS = {
    "not_reproduced",
    "patch_ineffective",
    "regression",
    "approval_denied",
    "github_error",
    "sandbox_error",
    "integrity_mismatch",
    "timeout",
    "install_failed",
    "issue_invalid",
}

# Phrases that try to steer the agent rather than describe a bug.
INJECTION_PATTERNS = [
    (r"ignore (all |any )?(previous|prior|above) (instructions|rules)", "override-instructions"),
    (
        r"(print|reveal|show|echo|dump|send|exfiltrate)\b.{0,40}"
        r"\b(env|environment|secret|token|api[_ -]?key|password|credential)",
        "secret-exfiltration",
    ),
    (r"\b(printenv|env\s*\|)|/proc/self/environ|\$\{?[A-Z_]*(TOKEN|SECRET|KEY)\}?", "secret-exfiltration"),
    (r"(skip|bypass|without|disable)\b.{0,30}\b(approval|review|sandbox)", "bypass-controls"),
    (r"(merge|push)\b.{0,30}\b(directly|to main|to master|without)", "unapproved-write"),
    (r"(curl|wget|nc|netcat)\s+\S*https?://", "network-egress"),
    (r"\byou are (now|an?)\b|\bsystem prompt\b|\bnew instructions\b", "role-override"),
]


def state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def evidence_path() -> Path:
    return state_dir() / "evidence.jsonl"


def state_path() -> Path:
    return state_dir() / "state.json"


def manifest_path() -> Path:
    return state_dir() / "manifest.json"


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        raise SystemExit("no CodeFix state: run `cf.py init` first")
    state: dict[str, Any] = json.loads(path.read_text())
    return state


def save_state(state: dict[str, Any]) -> None:
    state_path().write_text(json.dumps(state, indent=2))


def load_evidence() -> list[dict[str, Any]]:
    path = evidence_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def last_record(label: str, records: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    for record in reversed(records if records is not None else load_evidence()):
        if record["label"] == label:
            return record
    return None


def _truncate(text: str) -> str:
    if len(text) <= OUTPUT_LIMIT:
        return text
    half = OUTPUT_LIMIT // 2
    return f"{text[:half]}\n... [{len(text) - OUTPUT_LIMIT} chars truncated] ...\n{text[-half:]}"


# --- issue handling -------------------------------------------------------


@dataclass(frozen=True)
class IssueRef:
    owner: str
    repo: str
    number: int

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


_ISSUE_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/(\d+)/?$")
_ISSUE_SHORT = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#(\d+)$")


def parse_issue_ref(text: str) -> IssueRef:
    candidate = text.strip()
    match = _ISSUE_URL.match(candidate) or _ISSUE_SHORT.match(candidate)
    if match is None:
        raise ValueError(f"not a GitHub issue reference: {text!r}")
    owner, repo, number = match.groups()
    return IssueRef(owner=owner, repo=repo, number=int(number))


def check_issue_allowed(ref: IssueRef, allowed_repos: list[str]) -> None:
    allowed = {name.lower() for name in allowed_repos}
    if ref.full_name.lower() not in allowed:
        raise PermissionError(f"{ref.full_name} is not an allowed CodeFix target ({', '.join(sorted(allowed))})")


def check_issue_state(issue: dict[str, Any]) -> None:
    """Refuse issues that are closed or are pull requests."""
    if issue.get("pull_request"):
        raise ValueError("reference points to a pull request, not an issue")
    state = str(issue.get("state", "")).lower()
    if state != "open":
        raise ValueError(f"issue is {state or 'in an unknown state'}; CodeFix only works on open issues")


def scan_untrusted(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern, kind in INJECTION_PATTERNS:
            if re.search(pattern, line, flags=re.IGNORECASE):
                findings.append({"line": str(line_no), "kind": kind, "text": line.strip()[:200]})
                break
    return findings


# --- command evidence -----------------------------------------------------


def run_command(*, label: str, command: list[str], cwd: str | None, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    record: dict[str, Any] = {
        "label": label,
        "command": command,
        "cwd": cwd or os.getcwd(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "timed_out": False,
    }
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
        record.update(exit_code=proc.returncode, stdout=_truncate(proc.stdout), stderr=_truncate(proc.stderr))
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        record.update(exit_code=124, stdout=_truncate(out), stderr=_truncate(err), timed_out=True)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        record.update(exit_code=127, stdout="", stderr=f"{type(exc).__name__}: {exc}")
    record["duration_s"] = round(time.monotonic() - started, 3)
    with evidence_path().open("a") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def status_of(record: dict[str, Any] | None) -> str:
    if record is None:
        return "NOT RUN"
    if record["timed_out"]:
        return "TIMEOUT"
    return "PASS" if record["exit_code"] == 0 else "FAIL"


def classify_reproduction(records: list[dict[str, Any]]) -> str:
    """REPRODUCED only when the reproduction test fails while the baseline suite runs cleanly."""
    repro = last_record("reproduce", records)
    baseline = last_record("baseline", records)
    if repro is None or repro["timed_out"] or repro["exit_code"] in (124, 127):
        return "NOT_REPRODUCED"
    if repro["exit_code"] == 0:
        return "NOT_REPRODUCED"
    if baseline is None or baseline["timed_out"]:
        return "PARTIALLY_REPRODUCED"
    return "REPRODUCED"


# --- phase gates ----------------------------------------------------------


def _require(ok: bool, message: str, problems: list[str]) -> None:
    if not ok:
        problems.append(message)


def _after(record: dict[str, Any] | None, marker: int | None) -> bool:
    return record is not None and marker is not None and record.get("seq", 0) > marker


def gate_problems(target: str, state: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    for index, entry in enumerate(records):
        entry.setdefault("seq", index + 1)
    patched_at = state.get("patched_seq")

    if target == "CLONED":
        _require(status_of(last_record("clone", records)) == "PASS", "`clone` command has not succeeded", problems)
    elif target == "INSTALLED":
        _require(status_of(last_record("install", records)) == "PASS", "`install` command has not succeeded", problems)
    elif target == "BASELINE":
        baseline = last_record("baseline", records)
        _require(baseline is not None, "`baseline` test run is missing", problems)
        _require(baseline is None or not baseline["timed_out"], "`baseline` test run timed out", problems)
    elif target == "REPRODUCED":
        verdict = classify_reproduction(records)
        _require(verdict == "REPRODUCED", f"reproduction verdict is {verdict}", problems)
    elif target == "PATCHED":
        diff = last_record("diff", records)
        _require(status_of(diff) == "PASS" and bool(diff and diff["stdout"].strip()), "`diff` shows no change", problems)
    elif target == "VERIFIED_LOCAL":
        for label in ("reproduce-after", "regression"):
            record = last_record(label, records)
            _require(_after(record, patched_at), f"`{label}` was not run after the patch", problems)
            _require(status_of(record) == "PASS", f"`{label}` is {status_of(record)}", problems)
    elif target == "AWAITING_APPROVAL":
        _require(manifest_path().exists(), "tested-tree manifest is missing (run `cf.py manifest`)", problems)
        _require((state_dir() / "report.md").exists(), "verification report is missing (run `cf.py report`)", problems)
    elif target == "PR_VERIFIED":
        _require(status_of(last_record("integrity", records)) == "PASS", "PR integrity check has not passed", problems)
        _require(status_of(last_record("pr-tests", records)) == "PASS", "PR branch tests have not passed", problems)
    return problems


def advance(target: str, *, reason: str | None = None, detail: str | None = None) -> dict[str, Any]:
    state = load_state()
    current = state["phase"]
    if current in TERMINAL:
        raise PermissionError(f"workflow already ended in {current}; start a new run")
    records = load_evidence()
    if target == "STOPPED":
        if reason not in STOP_REASONS:
            raise ValueError(f"stop reason must be one of {sorted(STOP_REASONS)}")
        state.update(phase="STOPPED", stop_reason=reason, stop_detail=detail or "")
    else:
        if target not in PHASES:
            raise ValueError(f"unknown phase {target}")
        if PHASES.index(target) != PHASES.index(current) + 1:
            raise PermissionError(f"cannot move from {current} to {target}")
        problems = gate_problems(target, state, records)
        if problems:
            raise PermissionError("; ".join(problems))
        state["phase"] = target
        if target == "PATCHED":
            state["patched_seq"] = len(records)
        if detail:
            state.setdefault("notes", {})[target] = detail
    state.setdefault("history", []).append({"phase": state["phase"], "at": time.time()})
    save_state(state)
    return state


# --- tested-tree integrity -----------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(repo: Path) -> dict[str, Any]:
    """Record every changed file of the tested working tree with its content hash."""
    base = _git(repo, "rev-parse", "HEAD").strip()
    files: dict[str, str] = {}
    deleted: list[str] = []
    for line in _git(repo, "status", "--porcelain", "--untracked-files=all").splitlines():
        code, path = line[:2], line[3:]
        if " -> " in path or "R" in code:
            raise ValueError(f"renames are not supported by push_files: {path}")
        if "D" in code:
            deleted.append(path)
            continue
        if path.startswith(".codefix/") or "__pycache__" in path or path.endswith(".pyc"):
            continue
        files[path] = sha256_file(repo / path)
    if deleted:
        raise ValueError(f"deletions cannot be pushed with push_files: {', '.join(deleted)}")
    if not files:
        raise ValueError("working tree has no changes to push")
    return {"base_sha": base, "files": dict(sorted(files.items()))}


def push_payload(repo: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    payload = []
    for path, digest in manifest["files"].items():
        if sha256_file(repo / path) != digest:
            raise ValueError(f"{path} changed after the manifest was written; re-test before pushing")
        payload.append({"path": path, "content": (repo / path).read_text()})
    return payload


def verify_clone(*, manifest: dict[str, Any], clone: Path) -> list[str]:
    """Compare a fresh clone of the PR branch against the tested tree."""
    problems: list[str] = []
    changed = set(_git(clone, "diff", "--name-only", f"{manifest['base_sha']}..HEAD").split())
    expected = set(manifest["files"])
    for path in sorted(changed - expected):
        problems.append(f"PR changes untested file {path}")
    for path in sorted(expected - changed):
        problems.append(f"tested change to {path} is missing from the PR")
    for path in sorted(expected & changed):
        actual = sha256_file(clone / path)
        if actual != manifest["files"][path]:
            problems.append(f"{path} differs: tested {manifest['files'][path][:12]}, PR {actual[:12]}")
    return problems


# --- report ---------------------------------------------------------------

REPORT_FIELDS = [
    "issue",
    "repository",
    "problem",
    "root_cause",
    "reproduction",
    "fix",
    "security",
    "risk",
    "branch",
    "pr_title",
]


def _evidence_block(record: dict[str, Any] | None) -> str:
    if record is None:
        return "(not run)"
    output = (record["stdout"] + ("\n" + record["stderr"] if record["stderr"] else "")).strip()
    tail = "\n".join(output.splitlines()[-15:])
    return f"$ {' '.join(record['command'])}\nexit={record['exit_code']} duration={record['duration_s']}s\n{tail}"


def render_report(facts: dict[str, Any]) -> str:
    missing = [field for field in REPORT_FIELDS if not str(facts.get(field, "")).strip()]
    if missing:
        raise ValueError(f"report facts missing: {', '.join(missing)}")
    if str(facts["risk"]).upper() not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("risk must be LOW, MEDIUM or HIGH")
    records = load_evidence()
    manifest = json.loads(manifest_path().read_text())
    icon = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "TIMEOUT": "⏱ TIMEOUT", "NOT RUN": "— NOT RUN"}
    diff = last_record("diff", records)
    bar = "=" * 48
    lines = [
        bar,
        "CODEFIX VERIFICATION REPORT",
        bar,
        f"Issue: {facts['issue']}",
        f"Repository: {facts['repository']}",
        f"Problem: {facts['problem']}",
        f"Root Cause: {facts['root_cause']}",
        f"Reproduction: {facts['reproduction']}",
        f"Reproduction Verdict: {classify_reproduction(records)}",
        f"Baseline Suite: {icon[status_of(last_record('baseline', records))]}",
        f"Reproduction Test (before fix): {icon[status_of(last_record('reproduce', records))]}",
        "Reproduction Evidence:",
        _evidence_block(last_record("reproduce", records)),
        f"Fix: {facts['fix']}",
        "Files Changed:",
        *[f"  {path}  sha256={digest[:12]}" for path, digest in manifest["files"].items()],
        "Diff:",
        diff["stdout"].strip() if diff else "(no diff recorded)",
        f"Tests After Fix: {icon[status_of(last_record('reproduce-after', records))]}",
        f"Regression Tests: {icon[status_of(last_record('regression', records))]}",
        "Regression Evidence:",
        _evidence_block(last_record("regression", records)),
        f"Security Considerations: {facts['security']}",
        f"Risk: {str(facts['risk']).upper()}",
        f"Proposed Branch: {facts['branch']}",
        f"Proposed Pull Request: {facts['pr_title']}",
        "Actions requiring approval:",
        "  [1] Create branch",
        "  [2] Push tested changes",
        "  [3] Create Pull Request",
        bar,
    ]
    report = "\n".join(lines)
    (state_dir() / "report.md").write_text(report)
    return report


# --- CLI ------------------------------------------------------------------


def _fail(code: int, message: str) -> int:
    print(f"CODEFIX: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cf.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("issue", help="parse and authorize an issue reference")
    p.add_argument("ref")
    p.add_argument("--allowed-repo", action="append", required=True)
    p.add_argument("--issue-json", help="file with the issue as returned by issue_read")

    p = sub.add_parser("scan", help="flag instruction-like text in untrusted content")
    p.add_argument("file")

    p = sub.add_parser("init")
    p.add_argument("--issue", required=True)

    p = sub.add_parser("run", help="run a command and record evidence")
    p.add_argument("--label", required=True)
    p.add_argument("--cwd")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    p.add_argument("command", nargs=argparse.REMAINDER)

    p = sub.add_parser("phase", help="advance the workflow; refused unless evidence satisfies the gate")
    p.add_argument("target")
    p.add_argument("--reason")
    p.add_argument("--detail")

    sub.add_parser("classify")
    sub.add_parser("status")

    p = sub.add_parser("manifest")
    p.add_argument("--repo", required=True)

    p = sub.add_parser("push-payload")
    p.add_argument("--repo", required=True)

    p = sub.add_parser("verify-pr")
    p.add_argument("--clone", required=True)

    p = sub.add_parser("report")
    p.add_argument("--facts", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "issue":
        try:
            ref = parse_issue_ref(args.ref)
            check_issue_allowed(ref, args.allowed_repo)
            if args.issue_json:
                check_issue_state(json.loads(Path(args.issue_json).read_text()))
        except PermissionError as exc:
            return _fail(EXIT_NOT_ALLOWED, str(exc))
        except ValueError as exc:
            return _fail(EXIT_GATE, str(exc))
        print(json.dumps({"owner": ref.owner, "repo": ref.repo, "number": ref.number}))
        return 0

    if args.cmd == "scan":
        findings = scan_untrusted(Path(args.file).read_text())
        print(json.dumps({"untrusted_instruction_findings": findings}, indent=2))
        return 0

    if args.cmd == "init":
        ref = parse_issue_ref(args.issue)
        for stale in (evidence_path(), manifest_path(), state_dir() / "report.md"):
            stale.unlink(missing_ok=True)
        save_state({"issue": f"{ref.full_name}#{ref.number}", "phase": "INIT", "history": []})
        print(json.dumps(load_state()))
        return 0

    if args.cmd == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            return _fail(2, "run needs a command after --")
        record = run_command(label=args.label, command=command, cwd=args.cwd, timeout=args.timeout)
        print(json.dumps({k: record[k] for k in ("label", "exit_code", "timed_out", "duration_s")}))
        if record["stdout"]:
            print(record["stdout"])
        if record["stderr"]:
            print(record["stderr"], file=sys.stderr)
        return int(record["exit_code"])

    if args.cmd == "phase":
        try:
            state = advance(args.target, reason=args.reason, detail=args.detail)
        except (PermissionError, ValueError) as exc:
            return _fail(EXIT_GATE, f"refused: {exc}")
        print(json.dumps({"phase": state["phase"], "stop_reason": state.get("stop_reason")}))
        return 0

    if args.cmd == "classify":
        print(classify_reproduction(load_evidence()))
        return 0

    if args.cmd == "status":
        state = load_state()
        records = load_evidence()
        summary = [{"label": r["label"], "status": status_of(r), "exit_code": r["exit_code"]} for r in records]
        print(json.dumps({"state": state, "evidence": summary}, indent=2))
        return 0

    if args.cmd == "manifest":
        try:
            manifest = build_manifest(Path(args.repo))
        except (ValueError, subprocess.CalledProcessError) as exc:
            return _fail(EXIT_INTEGRITY, str(exc))
        manifest_path().write_text(json.dumps(manifest, indent=2))
        print(json.dumps(manifest, indent=2))
        return 0

    if args.cmd == "push-payload":
        try:
            payload = push_payload(Path(args.repo), json.loads(manifest_path().read_text()))
        except (ValueError, FileNotFoundError) as exc:
            return _fail(EXIT_INTEGRITY, str(exc))
        print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == "verify-pr":
        problems = verify_clone(manifest=json.loads(manifest_path().read_text()), clone=Path(args.clone))
        record = {
            "label": "integrity",
            "command": ["cf.py", "verify-pr", "--clone", args.clone],
            "cwd": os.getcwd(),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "timed_out": False,
            "exit_code": 0 if not problems else EXIT_INTEGRITY,
            "stdout": "tested tree == PR tree" if not problems else "",
            "stderr": "\n".join(problems),
            "duration_s": 0.0,
        }
        with evidence_path().open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        if problems:
            return _fail(EXIT_INTEGRITY, "INTEGRITY MISMATCH\n" + "\n".join(problems))
        print("INTEGRITY OK: PR branch matches the tested tree")
        return 0

    if args.cmd == "report":
        try:
            print(render_report(json.loads(Path(args.facts).read_text())))
        except (ValueError, FileNotFoundError) as exc:
            return _fail(EXIT_GATE, str(exc))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
