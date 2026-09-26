import sys

import cf
import pytest
from helpers import record, write_records


def test_run_records_real_exit_code_and_output():
    rec = cf.run_command(
        label="probe", command=[sys.executable, "-c", "import sys; print('hi'); sys.exit(3)"], cwd=None, timeout=10
    )
    assert rec["exit_code"] == 3 and rec["stdout"].strip() == "hi" and rec["duration_s"] >= 0
    assert cf.last_record("probe")["exit_code"] == 3


def test_run_timeout_is_recorded():
    rec = cf.run_command(label="slow", command=[sys.executable, "-c", "import time; time.sleep(5)"], cwd=None, timeout=1)
    assert rec["timed_out"] and rec["exit_code"] == 124
    assert cf.status_of(rec) == "TIMEOUT"


def test_sandbox_failure_missing_binary_is_recorded():
    rec = cf.run_command(label="clone", command=["definitely-not-a-binary"], cwd=None, timeout=5)
    assert rec["exit_code"] == 127 and "FileNotFoundError" in rec["stderr"]


def test_cli_run_propagates_exit_code():
    assert cf.main(["run", "--label", "t", "--", sys.executable, "-c", "raise SystemExit(4)"]) == 4


@pytest.mark.parametrize(
    ("records", "verdict"),
    [
        ([record("baseline", 0), record("reproduce", 1)], "REPRODUCED"),
        ([record("baseline", 0), record("reproduce", 0)], "NOT_REPRODUCED"),
        ([record("baseline", 0)], "NOT_REPRODUCED"),
        ([record("baseline", 0), record("reproduce", 124, timed_out=True)], "NOT_REPRODUCED"),
        ([record("baseline", 0), record("reproduce", 127)], "NOT_REPRODUCED"),
        ([record("reproduce", 1)], "PARTIALLY_REPRODUCED"),
    ],
)
def test_classify_reproduction(records, verdict):
    assert cf.classify_reproduction(records) == verdict


def _walk_to(phase):
    cf.main(["init", "--issue", "acme/demo#1"])
    for target in cf.PHASES[1 : cf.PHASES.index(phase) + 1]:
        cf.advance(target)


def test_happy_path_gates():
    cf.main(["init", "--issue", "acme/demo#1"])
    write_records(record("clone"), record("install"), record("baseline"), record("reproduce", 1))
    for phase in ("CLONED", "INSTALLED", "BASELINE", "REPRODUCED"):
        cf.advance(phase)
    write_records(record("diff", 0, stdout="--- a\n+++ b\n"))
    cf.advance("PATCHED")
    write_records(record("reproduce-after"), record("regression"))
    assert cf.advance("VERIFIED_LOCAL")["phase"] == "VERIFIED_LOCAL"


def test_reproduction_failure_blocks_patch():
    cf.main(["init", "--issue", "acme/demo#1"])
    write_records(record("clone"), record("install"), record("baseline"), record("reproduce", 0))
    for phase in ("CLONED", "INSTALLED", "BASELINE"):
        cf.advance(phase)
    with pytest.raises(PermissionError, match="NOT_REPRODUCED"):
        cf.advance("REPRODUCED")
    assert cf.main(["phase", "REPRODUCED"]) == cf.EXIT_GATE


def test_install_failure_blocks():
    cf.main(["init", "--issue", "acme/demo#1"])
    write_records(record("clone"), record("install", 1))
    cf.advance("CLONED")
    with pytest.raises(PermissionError, match="install"):
        cf.advance("INSTALLED")


def test_phases_cannot_be_skipped():
    cf.main(["init", "--issue", "acme/demo#1"])
    with pytest.raises(PermissionError, match="cannot move"):
        cf.advance("AWAITING_APPROVAL")


def _to_patched(after=None):
    after = after or (record("reproduce-after"), record("regression"))
    cf.main(["init", "--issue", "acme/demo#1"])
    write_records(record("clone"), record("install"), record("baseline"), record("reproduce", 1))
    for phase in ("CLONED", "INSTALLED", "BASELINE", "REPRODUCED"):
        cf.advance(phase)
    write_records(record("diff", 0, stdout="+fix"))
    cf.advance("PATCHED")
    write_records(*after)


def test_patch_that_does_not_fix_is_refused():
    _to_patched(after=(record("reproduce-after", 1), record("regression")))
    with pytest.raises(PermissionError, match="reproduce-after"):
        cf.advance("VERIFIED_LOCAL")


def test_regression_is_refused():
    _to_patched(after=(record("reproduce-after"), record("regression", 1)))
    with pytest.raises(PermissionError, match="regression"):
        cf.advance("VERIFIED_LOCAL")


def test_passing_tests_recorded_before_patch_do_not_count():
    cf.main(["init", "--issue", "acme/demo#1"])
    write_records(
        record("clone"),
        record("install"),
        record("baseline"),
        record("reproduce", 1),
        record("reproduce-after"),
        record("regression"),
    )
    for phase in ("CLONED", "INSTALLED", "BASELINE", "REPRODUCED"):
        cf.advance(phase)
    write_records(record("diff", 0, stdout="+fix"))
    cf.advance("PATCHED")
    with pytest.raises(PermissionError, match="not run after the patch"):
        cf.advance("VERIFIED_LOCAL")


def test_approval_required_before_writes():
    _to_patched()
    cf.advance("VERIFIED_LOCAL")
    with pytest.raises(PermissionError):
        cf.advance("PUSHED")
    with pytest.raises(PermissionError, match="manifest"):
        cf.advance("AWAITING_APPROVAL")


def test_approval_denied_is_terminal():
    _to_patched()
    cf.advance("VERIFIED_LOCAL")
    state = cf.advance("STOPPED", reason="approval_denied", detail="reviewer declined create_branch")
    assert state["stop_reason"] == "approval_denied"
    with pytest.raises(PermissionError, match="already ended"):
        cf.advance("AWAITING_APPROVAL")


def test_github_write_failure_stops_with_detail():
    _to_patched()
    state = cf.advance("STOPPED", reason="github_error", detail="push_files: 422 Reference does not exist")
    assert state["phase"] == "STOPPED" and "422" in state["stop_detail"]


def test_unknown_stop_reason_rejected():
    cf.main(["init", "--issue", "acme/demo#1"])
    with pytest.raises(ValueError):
        cf.advance("STOPPED", reason="because")


def test_pr_verified_requires_integrity_and_tests():
    state = {"phase": "PR_OPEN"}
    assert len(cf.gate_problems("PR_VERIFIED", state, [record("pr-tests")])) == 1
    assert len(cf.gate_problems("PR_VERIFIED", state, [record("integrity", 4), record("pr-tests")])) == 1
    assert cf.gate_problems("PR_VERIFIED", state, [record("integrity"), record("pr-tests")]) == []
