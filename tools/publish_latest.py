"""Copy the newest weekly report into web/latest/ (kept: .gitkeep) and print its period.

Usage: python tools/publish_latest.py build/report web/latest
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def fail(message: str) -> int:
    print(f"publish_latest: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="folder with the run's xlsx, eml and manifest")
    parser.add_argument("target", type=Path, help="web/latest")
    args = parser.parse_args(argv)
    manifests = sorted(args.source.glob("*.manifest.json")) if args.source.is_dir() else []
    if len(manifests) != 1:
        return fail(f"expected one *.manifest.json in {args.source}, found {len(manifests)}")
    manifest_path = manifests[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "built":
        return fail(f"{manifest_path.name} has status {manifest.get('status')!r}; nothing is published")
    files = [args.source / item["file"] for item in manifest.get("outputs", [])]
    missing = [path.name for path in files if not path.is_file()]
    if missing:
        return fail(f"listed in the manifest but missing: {', '.join(missing)}")
    args.target.mkdir(parents=True, exist_ok=True)
    for entry in args.target.iterdir():
        if entry.name == ".gitkeep":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    for path in [*files, manifest_path]:
        shutil.copyfile(path, args.target / path.name)
    shutil.copyfile(manifest_path, args.target / "manifest.json")
    print(manifest["period"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
