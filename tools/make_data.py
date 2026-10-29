"""Write the committed demo set: data/incoming/, end week 2025-W38, 8 weeks, profile demo, seed 2207."""

from __future__ import annotations

import argparse
from pathlib import Path

from buildreport.config import load_config
from buildreport.fixtures import DEFAULT_SEED, DEMO_END, DEMO_WEEKS, generate, write_fixtures

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "incoming")
    parser.add_argument("--config", type=Path, default=ROOT / "report.yaml")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    files = generate(cfg, DEMO_END, DEMO_WEEKS, deviations="demo", seed=DEFAULT_SEED)
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.xlsx"):
        old.unlink()
    write_fixtures(files, args.out)
    print(f"wrote {len(files)} files to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
