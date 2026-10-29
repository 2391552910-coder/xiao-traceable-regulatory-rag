"""Guard the repository's tracked paths for Windows checkouts."""
from __future__ import annotations

import re
import subprocess


_INVALID_COMPONENT = re.compile(r'[<>:"\\|?*\x00-\x1f]')
_RESERVED_COMPONENT = re.compile(
    r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',
    re.IGNORECASE,
)


def invalid_windows_component(part: str) -> bool:
    return (
        bool(_INVALID_COMPONENT.search(part))
        or part.endswith((" ", "."))
        or bool(_RESERVED_COMPONENT.fullmatch(part))
    )


def test_tracked_paths_are_windows_compatible() -> None:
    output = subprocess.check_output(["git", "ls-files", "-z"])
    paths = [path.decode("utf-8") for path in output.split(b"\0") if path]
    invalid = [
        path
        for path in paths
        if any(invalid_windows_component(part) for part in path.split("/"))
    ]
    assert not invalid, f"Paths invalid on Windows: {invalid}"


def test_knowledge_base_text_files_disable_line_ending_conversion() -> None:
    path = "data/knowledge_base/DOC304_证监会对＊ST普利重大财务造假案依法从严行政处罚.txt"
    output = subprocess.check_output(
        ["git", "check-attr", "-z", "text", "--", path]
    ).split(b"\0")
    assert output[1:3] == [b"text", b"unset"]
