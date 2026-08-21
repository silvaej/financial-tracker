"""Parse a Dependabot PR title for dependabot-autofix.yml.

Extracts the bumped package name and old/new versions from a title like
"(chore): Bump packaging from 26.2 to 26.3", and classifies the bump as
"major" or "patch-or-minor" by comparing only the leading release segment
via packaging.version (bumped packages don't all use strict X.Y.Z -- e.g.
packaging itself goes "26.2" -> "26.3").

Prints shell-eval-able `key=value` lines: package, old, new, classification.
`classification` is "unknown" if the title can't be parsed or a version
string isn't valid.
"""

import re
import sys

from packaging.version import InvalidVersion, Version


def parse(title: str) -> dict[str, str]:
    match = re.search(r"[Bb]ump\s+(\S+)\s+from\s+(\S+)\s+to\s+(\S+)", title)
    if not match:
        return {"package": "", "old": "", "new": "", "classification": "unknown"}
    package, old_s, new_s = match.groups()
    try:
        old, new = Version(old_s), Version(new_s)
    except InvalidVersion:
        return {"package": package, "old": old_s, "new": new_s, "classification": "unknown"}
    classification = "major" if old.release[0] != new.release[0] else "patch-or-minor"
    return {"package": package, "old": old_s, "new": new_s, "classification": classification}


if __name__ == "__main__":
    for key, value in parse(sys.argv[1]).items():
        print(f"{key}={value}")
