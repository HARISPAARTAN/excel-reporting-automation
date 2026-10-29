"""Copy the newest weekly report into web/latest/ (kept: .gitkeep) and print its period.

Every listed output is checked against the manifest's bytes and sha256 before the target is touched.

Usage: python tools/publish_latest.py build/report web/latest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

KEEP = ".gitkeep"
RESERVED = {KEEP, "manifest.json"}
REQUIRED = ("period", "status", "outputs")


class PublishError(Exception):
    """A reason to stop; raised before the target is touched."""


def fail(message: str) -> int:
    print(f"publish_latest: {message}", file=sys.stderr)
    return 1


def overlaps(first: Path, second: Path) -> bool:
    """True when the two folders are the same or one holds the other (symlinks resolved)."""
    first, second = first.resolve(), second.resolve()
    return first == second or first in second.parents or second in first.parents


def read_manifest(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        raise PublishError(f"{path.name} cannot be read as JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PublishError(f"{path.name} is not a JSON object")
    missing = [key for key in REQUIRED if key not in manifest]
    if missing:
        raise PublishError(f"{path.name} lacks the keys: {', '.join(missing)}")
    if not isinstance(manifest["period"], str) or not isinstance(manifest["outputs"], list):
        raise PublishError(f"{path.name}: period must be text and outputs a list")
    return raw, manifest


def listed_outputs(manifest: dict[str, Any], manifest_name: str) -> list[tuple[str, int, str]]:
    """The (name, bytes, sha256) of every output; names are plain file names that cannot escape the folder."""
    listed = []
    seen = {manifest_name, *RESERVED}
    for item in manifest["outputs"]:
        if not isinstance(item, dict):
            raise PublishError(f"{manifest_name}: every output must be an object")
        file, size, digest = item.get("file"), item.get("bytes"), item.get("sha256")
        if not isinstance(file, str) or not isinstance(digest, str):
            raise PublishError(f"{manifest_name}: every output needs a file name and a sha256")
        if not isinstance(size, int) or isinstance(size, bool):
            raise PublishError(f"{manifest_name}: {file!r} has no byte count")
        name = Path(file).name
        if name != file or name in ("", ".", "..") or "/" in file or "\\" in file:
            raise PublishError(f"{manifest_name}: {file!r} is not a plain file name")
        if name in seen:
            raise PublishError(f"{manifest_name}: {name!r} is listed twice or collides with a published name")
        seen.add(name)
        listed.append((name, size, digest))
    return listed


def read_verified(source: Path, listed: list[tuple[str, int, str]]) -> dict[str, bytes]:
    """The bytes of every output, read once and compared with the manifest."""
    missing = [name for name, _, _ in listed if not (source / name).is_file()]
    if missing:
        raise PublishError(f"listed in the manifest but missing: {', '.join(missing)}")
    blobs = {}
    problems = []
    for name, size, digest in listed:
        blob = (source / name).read_bytes()
        if len(blob) != size:
            problems.append(f"{name} has {len(blob):,} bytes, the manifest says {size:,}")
        elif hashlib.sha256(blob).hexdigest() != digest:
            problems.append(f"{name} has a different sha256 than the manifest")
        blobs[name] = blob
    if problems:
        raise PublishError("; ".join(problems) + "; nothing is published")
    return blobs


def clear(target: Path) -> None:
    """Empty the folder except .gitkeep; a symlinked entry is unlinked, never followed."""
    for entry in target.iterdir():
        if entry.name == KEEP:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def publish(source: Path, target: Path) -> str:
    if overlaps(source, target):
        raise PublishError(f"{source} and {target} are the same folder or one holds the other")
    manifests = sorted(source.glob("*.manifest.json")) if source.is_dir() else []
    if len(manifests) != 1:
        raise PublishError(f"expected one *.manifest.json in {source}, found {len(manifests)}")
    manifest_path = manifests[0]
    raw, manifest = read_manifest(manifest_path)
    if manifest["status"] != "built":
        raise PublishError(f"{manifest_path.name} has status {manifest['status']!r}; nothing is published")
    blobs = read_verified(source, listed_outputs(manifest, manifest_path.name))
    blobs[manifest_path.name] = raw
    blobs["manifest.json"] = raw
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise PublishError(f"{target} must be a plain folder")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".publish-", dir=target.parent))
    try:
        for name, blob in blobs.items():
            (stage / name).write_bytes(blob)
        target.mkdir(exist_ok=True)
        clear(target)
        for entry in stage.iterdir():
            entry.replace(target / entry.name)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return str(manifest["period"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="folder with the run's xlsx, eml and manifest")
    parser.add_argument("target", type=Path, help="web/latest")
    args = parser.parse_args(argv)
    try:
        period = publish(args.source, args.target)
    except PublishError as exc:
        return fail(str(exc))
    except OSError as exc:
        return fail(f"copy failed: {exc}")
    print(period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
