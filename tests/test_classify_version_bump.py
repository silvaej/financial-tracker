import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from classify_version_bump import parse  # noqa: E402


def test_patch_bump() -> None:
    result = parse("(chore): Bump mako from 1.3.12 to 1.4.1")
    assert result == {
        "package": "mako",
        "old": "1.3.12",
        "new": "1.4.1",
        "classification": "patch-or-minor",
    }


def test_two_component_bump() -> None:
    result = parse("(chore): Bump packaging from 26.2 to 26.3")
    assert result["package"] == "packaging"
    assert result["classification"] == "patch-or-minor"


def test_major_bump() -> None:
    result = parse("(chore): Bump fastapi from 0.115.0 to 1.0.0")
    assert result["classification"] == "major"


def test_unparseable_title() -> None:
    result = parse("(chore): Bump some dependency")
    assert result["classification"] == "unknown"
    assert result["package"] == ""
