"""
Patch reviewer — scans proposed patches for dangerous patterns before any apply.
"""

import re

_RULES: list[tuple[str, str]] = [
    (r"git\s+push",               "git push"),
    (r"rm\s+-rf",                  "rm -rf"),
    (r"shutil\.rmtree",            "shutil.rmtree"),
    (r"os\.remove\b",              "os.remove"),
    (r"os\.unlink\b",              "os.unlink"),
    (r"DROP\s+TABLE",              "DROP TABLE"),
    (r"DELETE\s+FROM",             "DELETE FROM (unguarded)"),
    (r"subprocess\.call|subprocess\.run|subprocess\.Popen",
                                   "subprocess exec (review required)"),
    (r"open\(['\"].*\.env",        "reading .env file"),
    (r"sk-[A-Za-z0-9\-]{20,}",    "API key literal"),
    (r"ANTHROPIC_API_KEY\s*=\s*['\"].+['\"]",  "hardcoded API key"),
]


def review(patch: str) -> tuple[bool, list[str]]:
    """
    Scan patch text for blocked patterns.
    Returns (is_safe, list_of_violation_descriptions).
    An empty violation list means the patch passed review.
    """
    violations = []
    for pattern, label in _RULES:
        if re.search(pattern, patch, re.IGNORECASE):
            violations.append(label)
    return len(violations) == 0, violations
