import json

import cf
import pytest
from helpers import record, write_records

FACTS = {
    "issue": "#1",
    "repository": "acme/codefix-demo",
    "problem": "1.10.0 rejected for >=1.9.0",
    "root_cause": "segments compared as strings",
    "reproduction": "tests/test_issue_1.py",
    "fix": "compare integer segments",
    "security": "no untrusted instructions found",
    "risk": "low",
    "branch": "codefix/issue-1",
    "pr_title": "Fix #1: numeric version comparison",
}


def _seed():
    cf.manifest_path().write_text(json.dumps({"base_sha": "abc", "files": {"app/versions.py": "f" * 64}}))
    write_records(
        record("baseline", 0, stdout="16 passed"),
        record("reproduce", 1, stdout="1 failed"),
        record("diff", 0, stdout="-a\n+b"),
        record("reproduce-after", 0, stdout="1 passed"),
        record("regression", 0, stdout="17 passed"),
    )


def test_report_statuses_come_from_evidence():
    _seed()
    report = cf.render_report(FACTS)
    assert "Reproduction Test (before fix): ❌ FAIL" in report
    assert "Tests After Fix: ✅ PASS" in report
    assert "Regression Tests: ✅ PASS" in report
    assert "Reproduction Verdict: REPRODUCED" in report
    assert "Risk: LOW" in report
    assert "[3] Create Pull Request" in report
    assert (cf.state_dir() / "report.md").exists()


def test_report_cannot_claim_pass_without_records():
    cf.manifest_path().write_text(json.dumps({"base_sha": "abc", "files": {"a.py": "0" * 64}}))
    write_records(record("baseline"), record("reproduce", 1))
    report = cf.render_report(FACTS)
    assert "Tests After Fix: — NOT RUN" in report
    assert "Regression Tests: — NOT RUN" in report


def test_report_requires_all_facts_and_valid_risk():
    _seed()
    with pytest.raises(ValueError, match="root_cause"):
        cf.render_report({**FACTS, "root_cause": " "})
    with pytest.raises(ValueError, match="risk"):
        cf.render_report({**FACTS, "risk": "unknown"})
