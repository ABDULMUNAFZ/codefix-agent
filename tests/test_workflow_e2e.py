"""Drive cf.py as the agent would, with real git and real pytest runs on the demo bug."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CF = [sys.executable, str(ROOT / "skills" / "codefix" / "scripts" / "cf.py")]
FIXTURE = ROOT / "tests" / "fixtures" / "demo"

REPRO_TEST = """from app.versions import satisfies


def test_issue_1_multi_digit_minor():
    assert satisfies("1.10.0", ">=1.9.0")
"""


def sh(*args, cwd, check=True):
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=check)


def cf(*args, cwd):
    return sh(*CF, *args, cwd=cwd, check=False)


@pytest.fixture
def origin(tmp_path):
    work = tmp_path / "seed"
    shutil.copytree(FIXTURE, work, ignore=shutil.ignore_patterns("__pycache__"))
    sh("git", "init", "-q", "-b", "main", cwd=work)
    sh("git", "-c", "user.email=t@e", "-c", "user.name=t", "add", "-A", cwd=work)
    sh("git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init", cwd=work)
    bare = tmp_path / "origin.git"
    sh("git", "clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)
    return bare


def test_full_workflow(tmp_path, origin):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    pytest_cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    assert cf("init", "--issue", "acme/codefix-demo#1", cwd=sandbox).returncode == 0

    assert cf("run", "--label", "clone", "--", "git", "clone", "-q", str(origin), "repo", cwd=sandbox).returncode == 0
    assert cf("phase", "CLONED", cwd=sandbox).returncode == 0
    assert cf("run", "--label", "install", "--", sys.executable, "-c", "import pytest", cwd=sandbox).returncode == 0
    assert cf("phase", "INSTALLED", cwd=sandbox).returncode == 0
    assert cf("run", "--label", "baseline", "--cwd", "repo", "--", *pytest_cmd, cwd=sandbox).returncode == 0
    assert cf("phase", "BASELINE", cwd=sandbox).returncode == 0

    # The patch must not be allowed before the bug is reproduced.
    assert cf("phase", "PATCHED", cwd=sandbox).returncode == 3

    repo = sandbox / "repo"
    (repo / "tests" / "test_issue_1.py").write_text(REPRO_TEST)
    repro = cf("run", "--label", "reproduce", "--cwd", "repo", "--", *pytest_cmd, "tests/test_issue_1.py", cwd=sandbox)
    assert repro.returncode == 1 and "1 failed" in repro.stdout
    assert cf("phase", "REPRODUCED", cwd=sandbox).returncode == 0

    versions = repo / "app" / "versions.py"
    versions.write_text(
        versions.read_text()
        .replace("def parse_version(text: str) -> tuple[str, ...]:", "def parse_version(text: str) -> tuple[int, ...]:")
        .replace('return tuple(match.group(1).split("."))', 'return tuple(int(part) for part in match.group(1).split("."))')
        .replace(
            "def _normalize(parts: tuple[str, ...], length: int) -> tuple[str, ...]:",
            "def _normalize(parts: tuple[int, ...], length: int) -> tuple[int, ...]:",
        )
        .replace('return parts + ("0",) * (length - len(parts))', "return parts + (0,) * (length - len(parts))")
    )
    assert cf("run", "--label", "diff", "--cwd", "repo", "--", "git", "diff", cwd=sandbox).returncode == 0
    assert cf("phase", "PATCHED", cwd=sandbox).returncode == 0
    assert (
        cf(
            "run", "--label", "reproduce-after", "--cwd", "repo", "--", *pytest_cmd, "tests/test_issue_1.py", cwd=sandbox
        ).returncode
        == 0
    )
    assert cf("run", "--label", "regression", "--cwd", "repo", "--", *pytest_cmd, cwd=sandbox).returncode == 0
    assert cf("phase", "VERIFIED_LOCAL", cwd=sandbox).returncode == 0

    manifest = json.loads(cf("manifest", "--repo", "repo", cwd=sandbox).stdout)
    assert set(manifest["files"]) == {"app/versions.py", "tests/test_issue_1.py"}
    facts = {
        "issue": "#1",
        "repository": "acme/codefix-demo",
        "problem": "p",
        "root_cause": "string compare",
        "reproduction": "tests/test_issue_1.py",
        "fix": "int segments",
        "security": "none",
        "risk": "LOW",
        "branch": "codefix/issue-1",
        "pr_title": "Fix #1: numeric comparison",
    }
    (sandbox / "facts.json").write_text(json.dumps(facts))
    report = cf("report", "--facts", "facts.json", cwd=sandbox)
    assert report.returncode == 0 and "Tests After Fix: ✅ PASS" in report.stdout
    assert cf("phase", "AWAITING_APPROVAL", cwd=sandbox).returncode == 0

    # Stand-in for approved create_branch + push_files: apply the payload to a new branch on origin.
    payload = json.loads(cf("push-payload", "--repo", "repo", cwd=sandbox).stdout)
    pusher = tmp_path / "pusher"
    sh("git", "clone", "-q", str(origin), str(pusher), cwd=tmp_path)
    sh("git", "checkout", "-q", "-b", "codefix/issue-1", cwd=pusher)
    for item in payload:
        (pusher / item["path"]).write_text(item["content"])
    sh("git", "add", "-A", cwd=pusher)
    sh("git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "Fix #1", cwd=pusher)
    sh("git", "push", "-q", "origin", "codefix/issue-1", cwd=pusher)
    for phase in ("PUSHED", "PR_OPEN"):
        assert cf("phase", phase, cwd=sandbox).returncode == 0

    assert (
        cf(
            "run",
            "--label",
            "pr-clone",
            "--",
            "git",
            "clone",
            "-q",
            "--branch",
            "codefix/issue-1",
            str(origin),
            "pr",
            cwd=sandbox,
        ).returncode
        == 0
    )
    assert cf("verify-pr", "--clone", "pr", cwd=sandbox).returncode == 0
    assert cf("run", "--label", "pr-tests", "--cwd", "pr", "--", *pytest_cmd, cwd=sandbox).returncode == 0
    final = cf("phase", "PR_VERIFIED", cwd=sandbox)
    assert final.returncode == 0 and "PR_VERIFIED" in final.stdout
