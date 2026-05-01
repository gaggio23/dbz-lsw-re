#!/usr/bin/env python3
"""Patch one card count in a copied DBZ LSW SRAM save."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from common import sha1, sha256


DEFAULT_CARD_CSV = Path("data/raw/known_cards_manual.csv")
DEFAULT_ARRAY_START = 0x037E
CARD_COUNT = 125
PATCHED_SAVE_DIR = Path("local_saves/patched")


def parse_int(raw_value: str, field_name: str) -> int:
    try:
        return int(raw_value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{field_name} must be an integer, got {raw_value!r}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path, help="Input SRAM save path")
    parser.add_argument("card_number", help="Card number, 1..125")
    parser.add_argument("count", help="New owned-card count, 0..255")
    parser.add_argument(
        "--array-start",
        default=DEFAULT_ARRAY_START,
        type=lambda value: parse_int(value, "array-start"),
        help=f"Card-count array start offset, default: 0x{DEFAULT_ARRAY_START:04X}",
    )
    parser.add_argument(
        "--card-csv",
        default=DEFAULT_CARD_CSV,
        type=Path,
        help=f"Card CSV used for names, default: {DEFAULT_CARD_CSV}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Patched save output path. Defaults to local_saves/patched/<save>_cardNN_countN.<ext>",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing patched output file")
    return parser.parse_args()


def load_card_names(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}

    names: dict[int, str] = {}
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            try:
                card_number = int((row.get("card_number") or "").strip(), 0)
            except ValueError:
                continue
            names[card_number] = (row.get("card_name") or "").strip()
    return names


def default_output_path(input_path: Path, card_number: int, count: int) -> Path:
    suffix = input_path.suffix or ".srm"
    return PATCHED_SAVE_DIR / f"{input_path.stem}_card{card_number:03d}_count{count}{suffix}"


def is_same_path(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False)


def main() -> int:
    args = parse_args()
    try:
        card_number = parse_int(args.card_number, "card_number")
        new_count = parse_int(args.count, "count")
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not 1 <= card_number <= CARD_COUNT:
        print(f"error: card_number must be from 1 to {CARD_COUNT}", file=sys.stderr)
        return 1
    if not 0 <= new_count <= 0xFF:
        print("error: count must be from 0 to 255", file=sys.stderr)
        return 1
    if args.array_start < 0:
        print("error: array-start must be non-negative", file=sys.stderr)
        return 1

    try:
        data = bytearray(args.save.read_bytes())
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    card_offset = args.array_start + card_number - 1
    if card_offset >= len(data):
        print(f"error: card offset 0x{card_offset:04X} is outside save size {len(data)}", file=sys.stderr)
        return 1
    if args.array_start + CARD_COUNT > len(data):
        print("error: card-count array does not fit in save", file=sys.stderr)
        return 1

    output_path = args.output or default_output_path(args.save, card_number, new_count)
    if is_same_path(args.save, output_path):
        print("error: refusing to overwrite the original save", file=sys.stderr)
        return 1
    if output_path.exists() and not args.force:
        print(f"error: output already exists: {output_path}; pass --force to overwrite", file=sys.stderr)
        return 1

    card_names = load_card_names(args.card_csv)
    old_count = data[card_offset]
    old_total = sum(data[args.array_start : args.array_start + CARD_COUNT])
    data[card_offset] = new_count
    new_total = sum(data[args.array_start : args.array_start + CARD_COUNT])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    patched = bytes(data)

    print(f"input: {args.save}")
    print(f"output: {output_path}")
    print(f"array_start: 0x{args.array_start:04X}")
    print(f"card_number: {card_number}")
    print(f"card_name: {card_names.get(card_number, '<unknown>')}")
    print(f"card_offset: 0x{card_offset:04X}")
    print(f"old_count: {old_count}")
    print(f"new_count: {new_count}")
    print(f"old_total_cards: {old_total}")
    print(f"new_total_cards: {new_total}")
    print("checksum_note: no checksum bytes were updated; this save format may not need one for this edit")
    print(f"sha1: {sha1(patched)}")
    print(f"sha256: {sha256(patched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
