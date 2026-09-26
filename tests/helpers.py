import json

import cf


def record(label, exit_code=0, stdout="", timed_out=False):
    return {
        "label": label,
        "command": ["x"],
        "cwd": ".",
        "started_at": "t",
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": "",
        "duration_s": 0.1,
    }


def write_records(*records):
    with cf.evidence_path().open("a") as handle:
        for item in records:
            handle.write(json.dumps(item) + "\n")
