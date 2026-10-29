"""Scrub check (umbrella section 12): AI tool and vendor names, the earlier demo company, authorship claims.

The terms are kept as SHA-256 hashes of their case-folded spelling, so this file does not spell them out. The
check reads every file git tracks or would add (ignored files are skipped): text files line by line, workbooks
by the text of their XML members (text and names; no cell references, values or formulas), e-mails by their
headers and text parts (the attached workbook lies next to them and is read on its own), plus every file path
and the commit messages in the clone. Text is split into words at anything that is not a letter or a digit;
single words, hyphen-joined word pairs and concatenated word pairs are compared, in the text as written and
with HTML entities decoded.

--extra FILE adds regular expressions, one per line (# starts a comment), for the banned list that is kept on
the owner's machine and never committed; a hit names the line of that list, never the matched text. Before
those patterns run, ALLOW masks the addresses at the invented domain cedarline.example that the spec
prescribes and the CSS keyword -apple-system of the kit's font stack (portfolio-kit's own scrub allows it too).

Usage: uv run python tools/checks/scrub.py [--extra PATH]   (PATH: a local file of extra patterns, never committed)
Exit codes: 0 clean, 1 hits, 2 usage error.
"""

from __future__ import annotations

import argparse
import email
import functools
import hashlib
import html
import re
import subprocess
import sys
import zipfile
from collections.abc import Iterable, Iterator
from email import policy
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
TERMS = frozenset(
    {
        "c857d09db23e6822e3600bc06ad8d58f92ed62bc8efd81c753f77048662cb97d",
        "c70eca6b0f88f44d81a41311647e50fda1ac454ec04ffd442b0eb4743a993131",
        "60965168ce762e949600281ba6d01fee136e5b6e8257b1f216f9025ed324474c",
        "7d3194f79e645c42e4396dda38be04766810ec6a00d00aced3ffc2a0a1f1a9ef",
        "3ea125d0bff386e6754b3782b300016fc79a9cf8f8669c0a5c3db64467ddb681",
        "5d72436256ada53828b51895a94bb8489e9f1ac4fe937a8024ef1594e7045ff6",
        "683ec9b4c215b8391f2749b55d645adcea53cf5c571a28d923a18078927d1097",
        "81007f7b79c7fec4d2f0dc38aabb461ed699bb998a4e4a72af0f6cc1ce49ee6e",
        "7df7f6ff005c12f2c11cb3d81767ba673eec86c8dbc976542fdd04e0307e8530",
    }
)
WORD = re.compile(r"[^\W_]+")
BINARY = frozenset({".png", ".pdf", ".woff2", ".ico", ".jpg", ".jpeg", ".gif"})
SKIP = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".hypothesis",
        "build",
        "reports",
        "dist",
        "_kit",
    }
)
Rule = tuple[int, re.Pattern[str]]  # (line in the extra list, compiled pattern)
ALLOW = re.compile(r"[\w.+-]+@cedarline\.example\b|-apple-system\b", re.IGNORECASE)
NAME_ATTRIBUTES = frozenset({"name", "displayName"})  # sheet, table, column and defined names
STRUCTURE = frozenset({"v", "f"})  # cell values and formulas: numbers and cell references, never prose


@functools.cache
def digest(word: str) -> str:
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


def candidates(line: str) -> Iterator[str]:
    """The case-folded words of a line, plus every adjacent pair joined by "-" and joined directly."""
    words = WORD.findall(line.casefold())
    yield from words
    for left, right in zip(words, words[1:], strict=False):
        yield f"{left}-{right}"
        yield left + right


def variants(text: str) -> tuple[str, ...]:
    decoded = html.unescape(text).replace("\u00a0", " ")
    return (text,) if decoded == text else (text, decoded)


def find_hits(text: str, terms: Iterable[str] = TERMS) -> list[int]:
    """Line numbers (from 1) that contain a term."""
    wanted = frozenset(terms)
    hits: set[int] = set()
    for variant in variants(text):
        for number, line in enumerate(variant.splitlines(), 1):
            if any(digest(word) in wanted for word in candidates(line)):
                hits.add(number)
    return sorted(hits)


def load_extra(path: Path) -> list[Rule]:
    rules: list[Rule] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip() and not line.startswith("#"):
            rules.append((number, re.compile(line, re.IGNORECASE)))
    return rules


def find_extra(text: str, rules: Iterable[Rule]) -> list[tuple[int, int]]:
    """(line in the text, line in the extra list) for every match."""
    rules = list(rules)
    hits: set[tuple[int, int]] = set()
    for variant in variants(text):
        for number, line in enumerate(variant.splitlines(), 1):
            masked = ALLOW.sub(" ", line)
            for rule_line, rule in rules:
                if rule.search(masked):
                    hits.add((number, rule_line))
    return sorted(hits)


def xml_text(data: bytes) -> str:
    """The prose of an XML part, one piece per line: element text and names, without cell references."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return data.decode("utf-8", "replace")
    pieces: list[str] = []
    for element in root.iter():
        pieces += [value for key, value in element.attrib.items() if key in NAME_ATTRIBUTES]
        if element.tag.rsplit("}", 1)[-1] not in STRUCTURE and element.text and element.text.strip():
            pieces.append(element.text)
        if element.tail and element.tail.strip():
            pieces.append(element.tail)
    return "\n".join(pieces)


def eml_text(data: bytes) -> str:
    """The headers and the decoded text parts of an e-mail, without the base64 of its attachments."""
    message = email.message_from_bytes(data, policy=policy.default)
    lines = [f"{key}: {value}" for key, value in message.items()]
    for part in message.walk():
        if part.get_content_maintype() == "text" and not part.is_attachment():
            lines.append(str(part.get_content()))
    return "\n".join(lines)


def repository_files(root: Path) -> list[Path]:
    """Files git tracks or would add; without git, every file outside the skipped folders."""
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        files = [path for path in root.rglob("*") if path.is_file()]
        return sorted(path for path in files if not SKIP.intersection(path.relative_to(root).parts))
    names = sorted({name for name in listed.decode("utf-8").split("\0") if name})
    return [root / name for name in names if (root / name).is_file()]


def commit_messages(root: Path) -> Iterator[tuple[str, str]]:
    try:
        log = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%H%x00%B%x00"], check=True, capture_output=True
        ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.CalledProcessError):
        return
    parts = log.split("\0")
    for sha, body in zip(parts[0::2], parts[1::2], strict=False):
        yield f"commit {sha.strip()[:7]}", body


def sources(root: Path, files: Iterable[Path]) -> Iterator[tuple[str, str]]:
    """(label, text): each file's path, then its text, a workbook's XML prose or an e-mail's text parts; last
    the commit messages."""
    for path in files:
        label = path.relative_to(root).as_posix()
        yield f"{label} (path)", label
        suffix = path.suffix.lower()
        if suffix in BINARY:
            continue
        if suffix == ".xlsx" and zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.namelist():
                    if member.endswith(".xml"):
                        yield f"{label}!{member}", xml_text(archive.read(member))
            continue
        if suffix == ".eml":
            yield label, eml_text(path.read_bytes())
            continue
        yield label, path.read_bytes().decode("utf-8", "replace")
    yield from commit_messages(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan the repository for banned terms.")
    parser.add_argument(
        "--extra",
        type=Path,
        metavar="PATH",
        help="a local file of extra patterns, never committed (default: none)",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    rules: list[Rule] = []
    if args.extra is not None:
        if not args.extra.is_file():
            print(f"scrub: {args.extra} not found", file=sys.stderr)
            return 2
        rules = load_extra(args.extra)
    root = args.root.resolve()
    files = repository_files(root)
    hits: set[str] = set()
    messages = 0
    for label, text in sources(root, files):
        if label.startswith("commit "):
            messages += 1
        for number in find_hits(text):
            hits.add(f"{label}:{number}: banned term")
        for number, rule_line in find_extra(text, rules):
            hits.add(f"{label}:{number}: matches line {rule_line} of {args.extra.name}")
    for hit in sorted(hits):
        print(hit)
    extra = f" and {len(rules)} extra patterns" if rules else ""
    verdict = f"{len(hits)} HITS" if hits else "CLEAN"
    scanned = f"{len(files)} files and {messages} commit messages for {len(TERMS)} terms{extra}"
    print(f"scrub: scanned {scanned}: {verdict}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
