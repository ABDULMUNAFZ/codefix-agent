import json
import subprocess

import cf
import pytest


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    (path / "app.py").write_text("x = 1\n")
    (path / "README.md").write_text("demo\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "init")
    return path


def test_manifest_records_modified_and_new_files(repo):
    (repo / "app.py").write_text("x = 2\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_issue_1.py").write_text("def test(): pass\n")
    manifest = cf.build_manifest(repo)
    assert set(manifest["files"]) == {"app.py", "tests/test_issue_1.py"}
    assert manifest["base_sha"] == git(repo, "rev-parse", "HEAD").strip()


def test_manifest_rejects_clean_tree_and_deletions(repo):
    with pytest.raises(ValueError, match="no changes"):
        cf.build_manifest(repo)
    (repo / "README.md").unlink()
    with pytest.raises(ValueError, match="deletions"):
        cf.build_manifest(repo)


def test_push_payload_is_exact_tested_content(repo):
    (repo / "app.py").write_text("x = 2\n")
    manifest = cf.build_manifest(repo)
    assert cf.push_payload(repo, manifest) == [{"path": "app.py", "content": "x = 2\n"}]
    (repo / "app.py").write_text("x = 3\n")
    with pytest.raises(ValueError, match="changed after the manifest"):
        cf.push_payload(repo, manifest)


def _pr_clone(repo, tmp_path, files):
    """Simulate the PR branch: base commit plus whatever was pushed."""
    clone = tmp_path / "pr"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=True)
    git(clone, "config", "user.email", "t@example.com")
    git(clone, "config", "user.name", "t")
    git(clone, "checkout", "-q", "-b", "codefix/issue-1")
    for path, content in files.items():
        target = clone / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "Fix #1")
    return clone


def test_successful_pr_verification(repo, tmp_path):
    (repo / "app.py").write_text("x = 2\n")
    manifest = cf.build_manifest(repo)
    cf.manifest_path().write_text(json.dumps(manifest))
    clone = _pr_clone(repo, tmp_path, {"app.py": "x = 2\n"})
    assert cf.verify_clone(manifest=manifest, clone=clone) == []
    assert cf.main(["verify-pr", "--clone", str(clone)]) == 0
    assert cf.status_of(cf.last_record("integrity")) == "PASS"


@pytest.mark.parametrize(
    ("pushed", "expected"),
    [
        ({"app.py": "x = 99\n"}, "app.py differs"),
        ({"app.py": "x = 2\n", "extra.py": "evil()\n"}, "untested file extra.py"),
        ({"README.md": "changed\n"}, "missing from the PR"),
    ],
)
def test_integrity_mismatch(repo, tmp_path, pushed, expected):
    (repo / "app.py").write_text("x = 2\n")
    manifest = cf.build_manifest(repo)
    cf.manifest_path().write_text(json.dumps(manifest))
    clone = _pr_clone(repo, tmp_path, pushed)
    problems = cf.verify_clone(manifest=manifest, clone=clone)
    assert any(expected in p for p in problems)
    assert cf.main(["verify-pr", "--clone", str(clone)]) == cf.EXIT_INTEGRITY
    assert cf.status_of(cf.last_record("integrity")) == "FAIL"
