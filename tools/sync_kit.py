"""Vendor portfolio-kit's dist/ at a tag into web/kit/, or check that web/kit/ still matches it.

  uv run python tools/sync_kit.py                     copy dist/ at v0.1.0 into web/kit/ and write web/kit/VERSION
  uv run python tools/sync_kit.py --check             compare web/kit/ with dist/MANIFEST.json at v0.1.0
  uv run python tools/sync_kit.py --check --kit _kit  the same against another clone (ci.yml checks the tag out)

The kit is read with `git -C <kit> archive <tag> dist`, unpacked with `tar -x` into a temporary folder and
checked against its own dist/MANIFEST.json before anything is copied. Nothing in the kit clone changes and no
network is used. The clone defaults to $PORTFOLIO_KIT, then a sibling clone ../portfolio-kit next to this repository.
Exit codes: 0 copied or matching, 1 differences, 2 git, tar or usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parents[1]
TAG = "v0.1.0"
DEFAULT_KIT = str(ROOT.parent / "portfolio-kit")  # a sibling clone of this repository
DEST = ROOT / "web" / "kit"
OWN = ("MANIFEST.json", "VERSION")  # files of a copy that MANIFEST.json does not list


def die(message: str) -> NoReturn:
    print(f"sync_kit: {message}", file=sys.stderr)
    raise SystemExit(2)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        die(f"{name} is not on PATH")
    return found


def display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def unpack(kit: str, tag: str, into: Path) -> Path:
    """git archive <tag> dist | tar -x -f - -C <into>; returns the unpacked dist/ folder."""
    archive = subprocess.run(
        [program("git"), "-C", kit, "archive", "--format=tar", tag, "dist"], capture_output=True
    )
    if archive.returncode != 0:
        die(f"cannot read dist/ at {tag} from {kit}: {archive.stderr.decode(errors='replace').strip()}")
    unpacked = subprocess.run(
        [program("tar"), "-x", "-f", "-", "-C", str(into)], input=archive.stdout, capture_output=True
    )
    if unpacked.returncode != 0:
        die(f"tar could not unpack dist/ at {tag}: {unpacked.stderr.decode(errors='replace').strip()}")
    dist = into / "dist"
    if not (dist / "MANIFEST.json").is_file():
        die(f"dist/MANIFEST.json is missing at {tag}")
    return dist


def read_tree(folder: Path) -> dict[str, bytes]:
    """{posix path below folder: bytes} of every file except MANIFEST.json and VERSION at the top."""
    files: dict[str, bytes] = {}
    for path in sorted(folder.rglob("*")):
        name = path.relative_to(folder).as_posix()
        if path.is_file() and name not in OWN:
            files[name] = path.read_bytes()
    return files


def compare(manifest: dict[str, Any], files: dict[str, bytes]) -> list[str]:
    """Differences between a MANIFEST.json and {path: bytes}; empty when they match."""
    want = {entry["file"]: entry for entry in manifest.get("files", [])}
    problems: list[str] = []
    for name in sorted(files):
        entry = want.pop(name, None)
        if entry is None:
            problems.append(f"not in MANIFEST.json: {name}")
        elif entry.get("bytes") != len(files[name]) or entry.get("sha256") != sha256(files[name]):
            problems.append(f"changed: {name}")
    problems.extend(f"missing: {name}" for name in sorted(want))
    return problems


def load_manifest(data: bytes, where: str) -> dict[str, Any]:
    try:
        manifest = json.loads(data)
    except ValueError as exc:
        die(f"{where} is not valid JSON: {exc}")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        die(f"{where} has no list of files")
    return manifest


def sync(kit: str, tag: str, dest: Path) -> int:
    if dest.resolve() in (ROOT, ROOT / "web", Path(kit).resolve()):
        die(f"refusing to replace {dest.as_posix()}: choose a folder such as web/kit")
    earlier_copy = dest.is_dir() and (not any(dest.iterdir()) or (dest / "MANIFEST.json").is_file())
    if dest.exists() and not earlier_copy:
        die(f"refusing to replace {dest.as_posix()}: it is not an earlier copy of the kit")
    with tempfile.TemporaryDirectory(prefix="sync-kit-") as tmp:
        dist = unpack(kit, tag, Path(tmp))
        manifest = load_manifest((dist / "MANIFEST.json").read_bytes(), f"dist/MANIFEST.json at {tag}")
        payload = read_tree(dist)
        problems = compare(manifest, payload)
        if problems:
            die(f"dist/ at {tag} does not match its own MANIFEST.json ({problems[0]})")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(dist, dest)
    (dest / "VERSION").write_bytes(f"{tag}\n".encode())
    print(f"copied {len(payload)} files of portfolio-kit {tag} into {display(dest)}")
    return 0


def check(kit: str, tag: str, dest: Path) -> int:
    local = dest / "MANIFEST.json"
    if not local.is_file():
        die(f"{display(dest)}/MANIFEST.json not found: copy the kit first with python tools/sync_kit.py")
    version = dest / "VERSION"
    pinned = version.read_text(encoding="utf-8").strip() if version.is_file() else None
    problems = [] if pinned == tag else [f"VERSION says {pinned}, expected {tag}"]
    with tempfile.TemporaryDirectory(prefix="sync-kit-") as tmp:
        upstream = (unpack(kit, tag, Path(tmp)) / "MANIFEST.json").read_bytes()
    if local.read_bytes() != upstream:
        problems.append(f"MANIFEST.json differs from dist/MANIFEST.json at {tag}")
    problems += compare(load_manifest(upstream, f"dist/MANIFEST.json at {tag}"), read_tree(dest))
    for problem in problems:
        print(problem)
    if problems:
        print(f"{display(dest)} differs from portfolio-kit {tag}: {len(problems)} problem(s)")
        return 1
    print(f"{display(dest)} matches portfolio-kit {tag}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vendor or check the portfolio-kit copy in web/kit/.")
    kit_default = os.environ.get("PORTFOLIO_KIT", DEFAULT_KIT)
    parser.add_argument("--kit", default=kit_default, help="clone of portfolio-kit")
    parser.add_argument("--tag", default=TAG, help=f"tag (or tree) of portfolio-kit, default {TAG}")
    parser.add_argument("--dest", type=Path, default=DEST, help="vendored folder, default web/kit")
    parser.add_argument("--check", action="store_true", help="compare instead of copying")
    args = parser.parse_args(argv)
    if not Path(args.kit).is_dir():
        die(f"no portfolio-kit clone at {args.kit}")
    return check(args.kit, args.tag, args.dest) if args.check else sync(args.kit, args.tag, args.dest)


if __name__ == "__main__":
    raise SystemExit(main())
