#!/usr/bin/env python3
"""Patch exactly one byte in a copied ROM for manual emulator validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import read_rom, sha1, sha256


PATCHED_DIR = Path("patched")


def parse_int(raw_value: str, field_name: str) -> int:
    try:
        return int(raw_value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{field_name} must be an integer, got {raw_value!r}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="Input ROM path")
    parser.add_argument("offset", help="File offset to patch, decimal or 0x-prefixed hex")
    parser.add_argument("value", help="New byte value, decimal or 0x-prefixed hex")
    parser.add_argument(
        "--output",
        type=Path,
        help="Patched ROM output path. Must be under patched/. Defaults to patched/<rom>_patch_<offset>_<value>.<ext>",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing patched output file")
    return parser.parse_args()


def default_output_path(input_path: Path, offset: int, value: int) -> Path:
    suffix = input_path.suffix or ".gbc"
    stem = input_path.stem
    return PATCHED_DIR / f"{stem}_patch_{offset:06X}_{value:02X}{suffix}"


def is_under_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(directory.resolve(strict=False))
    except ValueError:
        return False
    return True


def main() -> int:
    args = parse_args()
    try:
        offset = parse_int(args.offset, "offset")
        value = parse_int(args.value, "value")
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if offset < 0:
        print("error: offset must be non-negative", file=sys.stderr)
        return 1
    if not 0 <= value <= 0xFF:
        print("error: value must be one byte, 0..255", file=sys.stderr)
        return 1

    try:
        data = bytearray(read_rom(args.rom))
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if offset >= len(data):
        print(f"error: offset 0x{offset:06X} is outside ROM size {len(data)}", file=sys.stderr)
        return 1

    output_path = args.output or default_output_path(args.rom, offset, value)
    if not is_under_directory(output_path, PATCHED_DIR):
        print("error: output path must be under patched/", file=sys.stderr)
        return 1
    if args.rom.resolve(strict=False) == output_path.resolve(strict=False):
        print("error: refusing to overwrite the original ROM", file=sys.stderr)
        return 1
    if output_path.exists() and not args.force:
        print(f"error: output already exists: {output_path}; pass --force to overwrite", file=sys.stderr)
        return 1

    old_value = data[offset]
    data[offset] = value
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    patched = bytes(data)

    print(f"input: {args.rom}")
    print(f"output: {output_path}")
    print(f"offset: 0x{offset:06X}")
    print(f"old_value: 0x{old_value:02X} ({old_value})")
    print(f"new_value: 0x{value:02X} ({value})")
    print(f"sha1: {sha1(patched)}")
    print(f"sha256: {sha256(patched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
