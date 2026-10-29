"""Regenerate the demo set in a temporary folder and compare content fingerprints with data/incoming/."""

from __future__ import annotations

import argparse
from pathlib import Path

from buildreport.config import load_config
from buildreport.fixtures import fingerprint_folder, regenerate_fingerprints

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--committed", type=Path, default=ROOT / "data" / "incoming")
    parser.add_argument("--config", type=Path, default=ROOT / "report.yaml")
    args = parser.parse_args(argv)
    expected = regenerate_fingerprints(load_config(args.config))
    actual = fingerprint_folder(args.committed)
    problems = [f"missing: {name}" for name in sorted(set(expected) - set(actual))]
    problems += [f"unexpected: {name}" for name in sorted(set(actual) - set(expected))]
    problems += [
        f"content differs: {name}"
        for name in sorted(set(expected) & set(actual))
        if expected[name] != actual[name]
    ]
    for problem in problems:
        print(problem)
    if problems:
        print(f"fixtures differ from the generator: {len(problems)} problems; run tools/make_data.py")
        return 1
    print(f"fixtures match the generator: {len(actual)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
