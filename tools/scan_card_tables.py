#!/usr/bin/env python3
"""Find conservative card-stat table candidates from manually verified stats."""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from common import file_offset_to_gb_addr, read_rom


DEFAULT_KNOWN_CARDS = Path("data/raw/known_cards_manual.csv")
DEFAULT_OUTPUT = Path("data/candidates/card_table_candidates.csv")
FIELD_NAMES = ("cc", "atk", "acc")
FIELD_ORDERS = tuple(itertools.permutations(FIELD_NAMES))


@dataclass(frozen=True)
class KnownCard:
    card_name: str
    card_type: str
    cc: int
    atk: int
    acc: int
    notes: str

    def values_by_field(self) -> dict[str, int]:
        return {"cc": self.cc, "atk": self.atk, "acc": self.acc}


@dataclass(frozen=True)
class EncodedField:
    name: str
    value: int
    encoding: str
    payload: bytes


@dataclass(frozen=True)
class Match:
    card: KnownCard
    offset: int
    field_order: tuple[str, str, str]
    encodings: tuple[str, str, str]
    gaps: tuple[int, int]
    matched_bytes: bytes
    surrounding_bytes: bytes
    surrounding_start: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", default="baserom.gbc", help="ROM path, default: baserom.gbc")
    parser.add_argument(
        "--known-cards",
        default=DEFAULT_KNOWN_CARDS,
        type=Path,
        help=f"Manual card stat CSV, default: {DEFAULT_KNOWN_CARDS}",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help=f"Candidate export CSV, default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--max-gap",
        default=3,
        type=int,
        help="Maximum unknown bytes allowed between visible stat fields, default: 3",
    )
    parser.add_argument(
        "--context",
        default=16,
        type=int,
        help="Bytes of surrounding context on each side of a candidate, default: 16",
    )
    parser.add_argument(
        "--print-limit",
        default=200,
        type=int,
        help="Maximum candidates to print to stdout; CSV still receives all candidates, default: 200",
    )
    return parser.parse_args()


def parse_int(raw_value: str) -> int | None:
    value = raw_value.strip()
    if not value:
        return None
    try:
        parsed = int(value, 0)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def load_known_cards(path: Path) -> tuple[list[KnownCard], list[str]]:
    warnings: list[str] = []
    if not path.exists():
        return [], [f"known card CSV not found: {path}"]

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_columns = set(["card_name", "type", "cc", "atk", "acc", "notes"]) - set(reader.fieldnames or [])
        if missing_columns:
            joined = ", ".join(sorted(missing_columns))
            return [], [f"known card CSV is missing required columns: {joined}"]

        cards: list[KnownCard] = []
        for line_number, row in enumerate(reader, start=2):
            if not row or not any((value or "").strip() for value in row.values()):
                continue

            values = {field: parse_int(row.get(field, "")) for field in FIELD_NAMES}
            if any(values[field] is None for field in FIELD_NAMES):
                warnings.append(
                    f"line {line_number}: skipped {row.get('card_name', '').strip() or '<unnamed>'}; "
                    "cc/atk/acc must all be numeric"
                )
                continue

            cards.append(
                KnownCard(
                    card_name=(row.get("card_name") or "").strip(),
                    card_type=(row.get("type") or "").strip(),
                    cc=values["cc"] or 0,
                    atk=values["atk"] or 0,
                    acc=values["acc"] or 0,
                    notes=(row.get("notes") or "").strip(),
                )
            )

    return cards, warnings


def encode_value(name: str, value: int) -> list[EncodedField]:
    encodings: list[EncodedField] = []
    if value <= 0xFF:
        encodings.append(EncodedField(name, value, "u8", bytes([value])))
    if value <= 0xFFFF:
        little = value.to_bytes(2, byteorder="little")
        big = value.to_bytes(2, byteorder="big")
        encodings.append(EncodedField(name, value, "u16le", little))
        if big != little:
            encodings.append(EncodedField(name, value, "u16be", big))
    return encodings


Pattern = tuple[int | None, ...]


def build_patterns(
    card: KnownCard, max_gap: int
) -> Iterable[tuple[tuple[str, str, str], tuple[EncodedField, ...], Pattern, tuple[int, int]]]:
    values = card.values_by_field()
    for field_order in FIELD_ORDERS:
        encoding_options = [encode_value(field, values[field]) for field in field_order]
        for encoded_fields in itertools.product(*encoding_options):
            for first_gap in range(max_gap + 1):
                for second_gap in range(max_gap + 1):
                    pattern = tuple(encoded_fields[0].payload)
                    pattern += (None,) * first_gap
                    pattern += tuple(encoded_fields[1].payload)
                    pattern += (None,) * second_gap
                    pattern += tuple(encoded_fields[2].payload)
                    yield field_order, encoded_fields, pattern, (first_gap, second_gap)


def pattern_matches_at(data: bytes, offset: int, pattern: Pattern) -> bool:
    if offset + len(pattern) > len(data):
        return False

    for index, expected in enumerate(pattern):
        if expected is not None and data[offset + index] != expected:
            return False
    return True


def byte_counts(data: bytes) -> list[int]:
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    return counts


def find_pattern_offsets(data: bytes, pattern: Pattern, counts: list[int]) -> Iterable[int]:
    literal_indexes = [index for index, byte in enumerate(pattern) if byte is not None]
    if not literal_indexes:
        return

    anchor_index = min(literal_indexes, key=lambda index: counts[pattern[index] or 0])
    anchor_value = pattern[anchor_index]
    if anchor_value is None:
        return

    anchor = bytes([anchor_value])
    search_from = 0

    while True:
        anchor_offset = data.find(anchor, search_from)
        if anchor_offset < 0:
            return

        candidate_offset = anchor_offset - anchor_index
        if candidate_offset >= 0 and pattern_matches_at(data, candidate_offset, pattern):
            yield candidate_offset

        search_from = anchor_offset + 1


def find_matches(data: bytes, cards: Iterable[KnownCard], max_gap: int, context: int) -> list[Match]:
    matches: dict[tuple[str, int, tuple[str, str, str], tuple[str, str, str], tuple[int, int]], Match] = {}
    counts = byte_counts(data)

    for card in cards:
        for field_order, encoded_fields, pattern, gaps in build_patterns(card, max_gap):
            encoding_names = tuple(field.encoding for field in encoded_fields)
            for offset in find_pattern_offsets(data, pattern, counts):
                surrounding_start = max(0, offset - context)
                surrounding_end = min(len(data), offset + len(pattern) + context)
                key = (card.card_name, offset, field_order, encoding_names, gaps)
                matches[key] = Match(
                    card=card,
                    offset=offset,
                    field_order=field_order,
                    encodings=encoding_names,
                    gaps=gaps,
                    matched_bytes=data[offset : offset + len(pattern)],
                    surrounding_bytes=data[surrounding_start:surrounding_end],
                    surrounding_start=surrounding_start,
                )

    return sorted(matches.values(), key=lambda match: (match.offset, match.card.card_name, match.field_order, match.encodings, match.gaps))


def hex_bytes(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def write_candidates(path: Path, matches: Iterable[Match]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "card_name",
                "type",
                "cc",
                "atk",
                "acc",
                "file_offset",
                "bank",
                "cpu_address",
                "field_order",
                "field_encodings",
                "gaps",
                "matched_bytes",
                "surrounding_start",
                "surrounding_bytes",
                "notes",
            ],
        )
        writer.writeheader()
        for match in matches:
            address = file_offset_to_gb_addr(match.offset)
            writer.writerow(
                {
                    "card_name": match.card.card_name,
                    "type": match.card.card_type,
                    "cc": match.card.cc,
                    "atk": match.card.atk,
                    "acc": match.card.acc,
                    "file_offset": f"0x{match.offset:06X}",
                    "bank": f"0x{address.bank:02X}",
                    "cpu_address": f"0x{address.cpu_address:04X}",
                    "field_order": ",".join(match.field_order),
                    "field_encodings": ",".join(match.encodings),
                    "gaps": ",".join(str(gap) for gap in match.gaps),
                    "matched_bytes": hex_bytes(match.matched_bytes),
                    "surrounding_start": f"0x{match.surrounding_start:06X}",
                    "surrounding_bytes": hex_bytes(match.surrounding_bytes),
                    "notes": match.card.notes,
                }
            )


def print_match(match: Match) -> None:
    address = file_offset_to_gb_addr(match.offset)
    print(
        f"0x{match.offset:06X} "
        f"bank=0x{address.bank:02X} "
        f"cpu=0x{address.cpu_address:04X} "
        f"order={','.join(match.field_order)} "
        f"enc={','.join(match.encodings)} "
        f"gaps={','.join(str(gap) for gap in match.gaps)} "
        f"card={match.card.card_name or '<unnamed>'}"
    )
    print(f"  surrounding @ 0x{match.surrounding_start:06X}: {hex_bytes(match.surrounding_bytes)}")


def main() -> int:
    args = parse_args()
    rom_path = Path(args.rom)

    if args.max_gap < 0:
        print("error: --max-gap must be non-negative", file=sys.stderr)
        return 1
    if args.context < 0:
        print("error: --context must be non-negative", file=sys.stderr)
        return 1
    if args.print_limit < 0:
        print("error: --print-limit must be non-negative", file=sys.stderr)
        return 1

    try:
        data = read_rom(rom_path)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    cards, warnings = load_known_cards(args.known_cards)
    print(f"Loaded ROM: {rom_path} ({len(data)} bytes)")
    print(f"Known card CSV: {args.known_cards}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if not cards:
        write_candidates(args.output, [])
        print("No manually verified numeric card rows were available.")
        print(f"Wrote empty candidate CSV: {args.output}")
        print()
        print("Collect these values from the game UI before using this scanner:")
        print("  card_name,type,cc,atk,acc,notes")
        print("Use decimal numbers for cc/atk/acc and leave notes for source details such as save state, deck, or screen.")
        return 2

    matches = find_matches(data, cards, args.max_gap, args.context)
    write_candidates(args.output, matches)

    print(f"Numeric known cards scanned: {len(cards)}")
    print(f"Max gap between fields: {args.max_gap} byte(s)")
    print(f"Candidate matches: {len(matches)}")
    print(f"Wrote candidate CSV: {args.output}")

    if matches:
        print()
        for match in matches[: args.print_limit]:
            print_match(match)
        remaining = len(matches) - args.print_limit
        if remaining > 0:
            print()
            print(f"... omitted {remaining} additional candidate(s) from stdout; see {args.output}")
    else:
        print("No candidates found with the current values, field encodings, and gap limit.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
