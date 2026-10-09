"""Synchronize generated Phase 1.6 assets into Django static files."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "dist" / "greenhouse.glb"
DEFAULT_TARGET = PROJECT_ROOT / "digital_twin" / "static" / "digital_twin" / "models" / "greenhouse.glb"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_glb(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"GLB not found: {path}")
    with path.open("rb") as handle:
        if handle.read(4) != b"glTF":
            raise ValueError(f"Not a GLB 2.x file: {path}")


def sync(source: Path, target: Path, check_only: bool = False) -> bool:
    validate_glb(source)
    if check_only:
        validate_glb(target)
        return sha256(source) == sha256(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    validate_glb(target)
    return sha256(source) == sha256(target)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    source = args.source.resolve()
    target = args.target.resolve()
    try:
        matches = sync(source, target, args.check)
    except (OSError, ValueError) as exc:
        print(f"[GLB SYNC ERROR] {exc}", file=sys.stderr)
        return 1
    mode = "CHECK" if args.check else "SYNC"
    print(f"[GLB {mode}]")
    print(f"source: {source}")
    print(f"target: {target}")
    print(f"status: {'match' if matches else 'mismatch'}")
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
