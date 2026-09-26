"""Version parsing and requirement matching for plugin compatibility checks."""

from __future__ import annotations

import re

_VERSION_RE = re.compile(r"^\s*v?(\d+(?:\.\d+)*)\s*$")
_REQUIREMENT_RE = re.compile(r"^\s*(==|!=|>=|<=|>|<)\s*(\S+)\s*$")


class InvalidVersion(ValueError):
    pass


def parse_version(text: str) -> tuple[str, ...]:
    """Parse "1.2.3" (optionally prefixed with "v") into its release segments."""
    match = _VERSION_RE.match(text)
    if match is None:
        raise InvalidVersion(f"invalid version: {text!r}")
    return tuple(match.group(1).split("."))


def _normalize(parts: tuple[str, ...], length: int) -> tuple[str, ...]:
    # "1.2" and "1.2.0" are the same release.
    return parts + ("0",) * (length - len(parts))


def compare(a: str, b: str) -> int:
    """Return -1, 0 or 1 as version ``a`` is lower, equal or higher than ``b``."""
    pa, pb = parse_version(a), parse_version(b)
    length = max(len(pa), len(pb))
    na, nb = _normalize(pa, length), _normalize(pb, length)
    return (na > nb) - (na < nb)


def satisfies(version: str, requirement: str) -> bool:
    """Check ``version`` against a comma-separated requirement like ">=1.4, <2.0"."""
    for clause in requirement.split(","):
        if not clause.strip():
            continue
        match = _REQUIREMENT_RE.match(clause)
        if match is None:
            raise ValueError(f"invalid requirement clause: {clause!r}")
        op, target = match.groups()
        result = compare(version, target)
        ok = {
            "==": result == 0,
            "!=": result != 0,
            ">=": result >= 0,
            "<=": result <= 0,
            ">": result > 0,
            "<": result < 0,
        }[op]
        if not ok:
            return False
    return True
