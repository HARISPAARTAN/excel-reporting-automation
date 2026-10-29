"""Page weight check (umbrella section 7): the deployed page and everything it loads stays at or below 3 MB.

Counts every file under the site folder except the downloads in latest/ (.xlsx, .eml, .pdf and the
period-named manifest), latest/.gitkeep and the rendered previews, and reserves 400 KB for each of the five
previews instead: the most tools/render_sheets.py lets through, so the check holds before and after a render.
Usage: uv run python tools/checks/page_weight.py web
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LIMIT = 3_000_000
PREVIEWS = 5
PREVIEW_BYTES = 400_000
DOWNLOADS = (".xlsx", ".eml", ".pdf", ".manifest.json")


def counted(name: str) -> bool:
    if not name.startswith("latest/"):
        return True
    return not (name.endswith(DOWNLOADS) or name.startswith("latest/preview/") or name == "latest/.gitkeep")


def measure(web: Path) -> tuple[int, list[tuple[str, int]]]:
    """(total bytes including the preview reserve, [(path, bytes)] of the counted files sorted by path)."""
    items = []
    for path in web.rglob("*"):
        name = path.relative_to(web).as_posix()
        if path.is_file() and counted(name):
            items.append((name, path.stat().st_size))
    items.sort()
    return sum(size for _, size in items) + PREVIEWS * PREVIEW_BYTES, items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the weight of the Pages site.")
    parser.add_argument("web", type=Path, help="the site folder, web")
    args = parser.parse_args(argv)
    if not (args.web / "index.html").is_file():
        print(f"page_weight: {args.web.as_posix()}/index.html not found", file=sys.stderr)
        return 2
    total, items = measure(args.web)
    for name, size in sorted(items, key=lambda item: (-item[1], item[0]))[:5]:
        print(f"{size:>11,}  {name}")
    print(f"{PREVIEWS * PREVIEW_BYTES:>11,}  latest/preview/*.png (reserved, {PREVIEWS} x {PREVIEW_BYTES:,})")
    verdict = "ok" if total <= LIMIT else "TOO HEAVY"
    print(f"page weight {total:,} bytes ({len(items)} files and the reserve), limit {LIMIT:,}: {verdict}")
    return 0 if total <= LIMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
