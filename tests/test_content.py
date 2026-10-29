"""Content rule: every e-mail address in the repository ends in .example (the GitHub bot address excepted)."""

import os
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = re.compile(r"[A-Za-z0-9._%+\-\[\]]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
ALLOWED = {"41898282+github-actions[bot]@users.noreply.github.com"}
SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".hypothesis",
    "__pycache__",
    "build",
    "reports",
    "dist",
    "_kit",
    "node_modules",
}
BINARY = {".png", ".pdf", ".woff2", ".ico"}


def iter_texts():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(folder) / name
            if path.suffix in BINARY:
                continue
            if path.suffix == ".xlsx":
                try:
                    with zipfile.ZipFile(path) as archive:
                        for member in archive.namelist():
                            if member.endswith(".xml"):
                                yield f"{path}!{member}", archive.read(member).decode("utf-8", "replace")
                except zipfile.BadZipFile:
                    continue
                continue
            try:
                yield str(path), path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue


def test_every_address_ends_in_example():
    offenders = []
    for where, text in iter_texts():
        for address in ADDRESS.findall(text):
            if address in ALLOWED or address.lower().endswith(".example"):
                continue
            offenders.append(f"{where}: {address}")
    assert offenders == []
