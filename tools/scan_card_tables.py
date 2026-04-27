#!/usr/bin/env python3
"""Conservatively scan for card numeric data as records or parallel arrays."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from common import file_offset_to_gb_addr, read_rom


DEFAULT_KNOWN_CARDS = Path("data/raw/known_cards_manual.csv")
DEFAULT_RECORD_OUTPUT = Path("data/candidates/card_table_candidates.csv")
DEFAULT_ARRAY_OUTPUT = Path("data/candidates/card_parallel_array_candidates.csv")
DEFAULT_JSON_OUTPUT = Path("data/candidates/card_table_candidates.json")
NUMERIC_FIELDS = ("cc", "atk", "acc")
BLANK_NUMERIC_VALUES = {"", "--", "n/a", "na", "none", "null"}
CARD_TYPES = {"command", "damage", "beam", "support", "defense", "special"}
TYPE_ALIASES = {
    "command": "command",
    "damage": "damage",
    "beam": "beam",
    "support": "support",
    "item": "support",
    "defense": "defense",
    "avoid": "defense",
    "special": "special",
}
LOW_INFORMATION_VALUES = {0: 0.15, 1: 0.2, 2: 0.25, 10: 0.4}


@dataclass(frozen=True)
class CardRow:
    row_index: int
    card_number: int | None
    card_name: str
    card_type: str
    cc: int | None
    atk: int | None
    acc: int | None
    rarity: int | None
    notes: str

    def value_for(self, field_name: str) -> int | None:
        return getattr(self, field_name)


@dataclass(frozen=True)
class FixedFieldHit:
    field_name: str
    field_offset: int
    match_count: int
    weighted_score: float
    matched_rows: tuple[int, ...]


@dataclass(frozen=True)
class FixedRecordCandidate:
    candidate_type: str
    offset: int
    record_size: int
    field_hits: tuple[FixedFieldHit, ...]
    matched_value_count: int
    matched_row_count: int
    score: float
    surrounding_start: int
    surrounding_bytes: bytes


@dataclass
class ParallelArrayCandidate:
    candidate_type: str
    field_name: str
    offset: int
    match_count: int
    matched_row_count: int
    longest_run: int
    score: float
    surrounding_start: int
    surrounding_bytes: bytes
    near_fields: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", default="baserom.gbc", help="ROM path, default: baserom.gbc")
    parser.add_argument(
        "--known-cards",
        default=DEFAULT_KNOWN_CARDS,
        type=Path,
        help=f"Card CSV, default: {DEFAULT_KNOWN_CARDS}",
    )
    parser.add_argument(
        "--record-output",
        default=DEFAULT_RECORD_OUTPUT,
        type=Path,
        help=f"Fixed-width record candidate CSV, default: {DEFAULT_RECORD_OUTPUT}",
    )
    parser.add_argument(
        "--array-output",
        default=DEFAULT_ARRAY_OUTPUT,
        type=Path,
        help=f"Parallel-array candidate CSV, default: {DEFAULT_ARRAY_OUTPUT}",
    )
    parser.add_argument(
        "--json-output",
        default=DEFAULT_JSON_OUTPUT,
        type=Path,
        help=f"Optional combined JSON candidate export, default: {DEFAULT_JSON_OUTPUT}",
    )
    parser.add_argument("--record-size-min", default=3, type=int, help="Minimum record size to test, default: 3")
    parser.add_argument("--record-size-max", default=32, type=int, help="Maximum record size to test, default: 32")
    parser.add_argument(
        "--context",
        default=16,
        type=int,
        help="Context bytes on each side of candidate offset; capped at 16, default: 16",
    )
    parser.add_argument(
        "--top-records",
        default=50,
        type=int,
        help="Maximum fixed-width record candidates to export, default: 50",
    )
    parser.add_argument(
        "--top-arrays",
        default=50,
        type=int,
        help="Maximum parallel-array candidates to export, default: 50",
    )
    parser.add_argument(
        "--print-limit",
        default=5,
        type=int,
        help="Maximum candidates of each type to print to stdout, default: 5",
    )
    parser.add_argument(
        "--anchor-count",
        default=12,
        type=int,
        help="High-information rows used to seed candidate starts, default: 12",
    )
    parser.add_argument(
        "--start-limit",
        default=800,
        type=int,
        help="Candidate starts evaluated per field/offset after anchor scoring, default: 800",
    )
    parser.add_argument(
        "--field-hit-limit",
        default=40,
        type=int,
        help="Field hits kept per field/offset in fixed-width mode, default: 40",
    )
    parser.add_argument(
        "--min-record-field-matches",
        default=10,
        type=int,
        help="Minimum exact matches for one fixed-width field offset, default: 10",
    )
    parser.add_argument(
        "--min-record-fields",
        default=2,
        type=int,
        help="Minimum fields needed for a fixed-width record candidate, default: 2",
    )
    parser.add_argument(
        "--min-record-total-matches",
        default=45,
        type=int,
        help="Minimum total field-value matches for a fixed-width candidate, default: 45",
    )
    parser.add_argument(
        "--min-array-matches",
        default=16,
        type=int,
        help="Minimum exact matches for one parallel-array candidate, default: 16",
    )
    parser.add_argument(
        "--min-array-run",
        default=6,
        type=int,
        help="Minimum consecutive nonblank visible-order matches for one array candidate, default: 6",
    )
    parser.add_argument(
        "--near-distance",
        default=512,
        type=int,
        help="Distance in bytes used to report nearby parallel arrays, default: 512",
    )
    return parser.parse_args()


def parse_optional_int(raw_value: str | None, field_name: str, warnings: list[str], line_number: int) -> int | None:
    value = (raw_value or "").strip()
    if value.lower() in BLANK_NUMERIC_VALUES:
        return None
    try:
        parsed = int(value, 0)
    except ValueError:
        warnings.append(f"line {line_number}: {field_name}={value!r} is not numeric; treating as blank")
        return None
    if parsed < 0:
        warnings.append(f"line {line_number}: {field_name}={parsed} is negative; treating as blank")
        return None
    return parsed


def warn_out_of_range(
    value: int | None, field_name: str, minimum: int, maximum: int, warnings: list[str], line_number: int
) -> int | None:
    if value is None:
        return None
    if minimum <= value <= maximum:
        return value
    warnings.append(
        f"line {line_number}: {field_name}={value} is outside expected range {minimum}..{maximum}; treating as blank"
    )
    return None


def normalize_type(raw_value: str | None, warnings: list[str], line_number: int) -> str:
    raw_type = (raw_value or "").strip().lower()
    if not raw_type:
        return ""
    card_type = TYPE_ALIASES.get(raw_type)
    if card_type is None:
        warnings.append(f"line {line_number}: type={raw_type!r} is not in {sorted(CARD_TYPES)}; preserving blank type")
        return ""
    return card_type


def load_cards(path: Path) -> tuple[list[CardRow], list[str]]:
    warnings: list[str] = []
    if not path.exists():
        return [], [f"card CSV not found: {path}"]

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = set(reader.fieldnames or [])
        required_columns = {"card_name", "cc", "atk", "acc"}
        missing_columns = required_columns - fieldnames
        if missing_columns:
            joined = ", ".join(sorted(missing_columns))
            return [], [f"card CSV is missing required columns: {joined}"]

        pending_rows: list[dict[str, object]] = []
        for line_number, raw_row in enumerate(reader, start=2):
            row = {key: (value or "").strip() for key, value in raw_row.items()}
            if not any(row.values()):
                continue

            card_number = parse_optional_int(row.get("card_number"), "card_number", warnings, line_number)
            card_number = warn_out_of_range(card_number, "card_number", 1, 125, warnings, line_number)
            cc = parse_optional_int(row.get("cc"), "cc", warnings, line_number)
            cc = warn_out_of_range(cc, "cc", 0, 33, warnings, line_number)
            atk = parse_optional_int(row.get("atk"), "atk", warnings, line_number)
            acc = parse_optional_int(row.get("acc"), "acc", warnings, line_number)
            acc = warn_out_of_range(acc, "acc", 20, 100, warnings, line_number)
            if acc is not None and acc % 5 != 0:
                warnings.append(f"line {line_number}: acc={acc} is not a multiple of 5; treating as blank")
                acc = None
            rarity = parse_optional_int(row.get("rarity"), "rarity", warnings, line_number)
            rarity = warn_out_of_range(rarity, "rarity", 1, 3, warnings, line_number)

            pending_rows.append(
                {
                    "line_number": line_number,
                    "card_number": card_number,
                    "card_name": row.get("card_name", ""),
                    "card_type": normalize_type(row.get("type"), warnings, line_number),
                    "cc": cc,
                    "atk": atk,
                    "acc": acc,
                    "rarity": rarity,
                    "notes": row.get("notes", ""),
                }
            )

    if not pending_rows:
        return [], warnings

    card_numbers = [row["card_number"] for row in pending_rows]
    use_card_number_order = (
        all(number is not None for number in card_numbers)
        and len(set(card_numbers)) == len(pending_rows)
        and min(card_numbers) == 1
        and max(card_numbers) == len(pending_rows)
    )
    if not use_card_number_order:
        warnings.append("card_number is incomplete or not consecutive; using visible CSV row order as row_index")

    cards: list[CardRow] = []
    for visible_index, row in enumerate(pending_rows):
        row_index = int(row["card_number"]) - 1 if use_card_number_order else visible_index
        cards.append(
            CardRow(
                row_index=row_index,
                card_number=row["card_number"],  # type: ignore[arg-type]
                card_name=str(row["card_name"]),
                card_type=str(row["card_type"]),
                cc=row["cc"],  # type: ignore[arg-type]
                atk=row["atk"],  # type: ignore[arg-type]
                acc=row["acc"],  # type: ignore[arg-type]
                rarity=row["rarity"],  # type: ignore[arg-type]
                notes=str(row["notes"]),
            )
        )

    cards.sort(key=lambda card: card.row_index)
    expected_indexes = list(range(len(cards)))
    actual_indexes = [card.row_index for card in cards]
    if actual_indexes != expected_indexes:
        warnings.append("row indexes are not contiguous; candidate offsets may not represent full visible order")
    if len(cards) != 125:
        warnings.append(f"expected 125 card rows, found {len(cards)}")

    return cards, warnings


def hex_bytes(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def byte_window(data: bytes, offset: int, context: int) -> tuple[int, bytes]:
    capped_context = min(max(context, 0), 16)
    start = max(0, offset - capped_context)
    end = min(len(data), offset + capped_context)
    return start, data[start:end]


def numeric_values(cards: Iterable[CardRow], field_name: str) -> list[tuple[int, int]]:
    values: list[tuple[int, int]] = []
    for card in cards:
        value = card.value_for(field_name)
        if value is not None and 0 <= value <= 0xFF:
            values.append((card.row_index, value))
    return values


def build_value_weights(cards: list[CardRow]) -> dict[str, dict[int, float]]:
    weights_by_field: dict[str, dict[int, float]] = {}
    for field_name in NUMERIC_FIELDS:
        values = [value for _row_index, value in numeric_values(cards, field_name)]
        counts = Counter(values)
        total = len(values)
        field_weights: dict[int, float] = {}
        for value, count in counts.items():
            rarity_score = 1.0 + math.log2(total / count) if count else 1.0
            if value in LOW_INFORMATION_VALUES:
                rarity_score *= LOW_INFORMATION_VALUES[value]
            elif value <= 5:
                rarity_score *= 0.65
            elif value % 10 == 0:
                rarity_score *= 0.85
            field_weights[value] = rarity_score
        weights_by_field[field_name] = field_weights
    return weights_by_field


def positions_for_value(data: bytes, value: int, cache: dict[int, tuple[int, ...]]) -> tuple[int, ...]:
    if value in cache:
        return cache[value]

    positions: list[int] = []
    needle = bytes([value])
    search_from = 0
    while True:
        found_at = data.find(needle, search_from)
        if found_at < 0:
            break
        positions.append(found_at)
        search_from = found_at + 1

    cache[value] = tuple(positions)
    return cache[value]


def choose_anchors(
    data: bytes,
    cards: list[CardRow],
    field_name: str,
    value_weights: dict[int, float],
    position_cache: dict[int, tuple[int, ...]],
    anchor_count: int,
) -> list[tuple[int, int, float, tuple[int, ...]]]:
    anchors: list[tuple[float, int, int, float, tuple[int, ...]]] = []
    for row_index, value in numeric_values(cards, field_name):
        positions = positions_for_value(data, value, position_cache)
        if not positions:
            continue
        rom_rarity = math.log2((len(data) + 1) / (len(positions) + 1))
        weight = value_weights.get(value, 1.0)
        anchor_score = weight * max(rom_rarity, 0.1)
        anchors.append((anchor_score, row_index, value, weight, positions))

    anchors.sort(reverse=True)
    return [(row_index, value, weight, positions) for _score, row_index, value, weight, positions in anchors[:anchor_count]]


def evaluate_fixed_field(
    data: bytes,
    cards: list[CardRow],
    field_name: str,
    record_size: int,
    field_offset: int,
    table_start: int,
    value_weights: dict[int, float],
) -> FixedFieldHit:
    matched_rows: list[int] = []
    weighted_score = 0.0
    for card in cards:
        value = card.value_for(field_name)
        if value is None or not 0 <= value <= 0xFF:
            continue
        byte_offset = table_start + card.row_index * record_size + field_offset
        if data[byte_offset] == value:
            matched_rows.append(card.row_index)
            weighted_score += value_weights.get(value, 1.0)

    return FixedFieldHit(
        field_name=field_name,
        field_offset=field_offset,
        match_count=len(matched_rows),
        weighted_score=weighted_score,
        matched_rows=tuple(matched_rows),
    )


def find_fixed_field_hits(
    data: bytes,
    cards: list[CardRow],
    field_name: str,
    record_size: int,
    field_offset: int,
    value_weights: dict[int, float],
    anchors: list[tuple[int, int, float, tuple[int, ...]]],
    min_matches: int,
    start_limit: int,
    field_hit_limit: int,
) -> list[tuple[int, FixedFieldHit]]:
    table_span = len(cards) * record_size
    if table_span + field_offset > len(data):
        return []

    start_scores: dict[int, float] = defaultdict(float)
    start_anchor_hits: Counter[int] = Counter()
    max_start = len(data) - table_span
    for row_index, _value, weight, positions in anchors:
        row_offset = row_index * record_size + field_offset
        for position in positions:
            table_start = position - row_offset
            if 0 <= table_start <= max_start:
                start_scores[table_start] += weight
                start_anchor_hits[table_start] += 1

    ranked_starts = sorted(
        start_scores,
        key=lambda start: (start_anchor_hits[start], start_scores[start], -start),
        reverse=True,
    )[:start_limit]

    hits: list[tuple[int, FixedFieldHit]] = []
    for table_start in ranked_starts:
        hit = evaluate_fixed_field(data, cards, field_name, record_size, field_offset, table_start, value_weights)
        if hit.match_count >= min_matches:
            hits.append((table_start, hit))

    hits.sort(key=lambda item: (item[1].weighted_score, item[1].match_count), reverse=True)
    return hits[:field_hit_limit]


def select_distinct_field_hits(hits: Iterable[FixedFieldHit]) -> tuple[FixedFieldHit, ...]:
    by_field: dict[str, list[FixedFieldHit]] = defaultdict(list)
    for hit in hits:
        by_field[hit.field_name].append(hit)

    selected: list[FixedFieldHit] = []
    used_offsets: set[int] = set()
    for field_name in NUMERIC_FIELDS:
        field_hits = sorted(by_field.get(field_name, []), key=lambda hit: (hit.weighted_score, hit.match_count), reverse=True)
        for hit in field_hits:
            if hit.field_offset not in used_offsets:
                selected.append(hit)
                used_offsets.add(hit.field_offset)
                break

    return tuple(selected)


def find_fixed_record_candidates(
    data: bytes,
    cards: list[CardRow],
    weights_by_field: dict[str, dict[int, float]],
    context: int,
    record_size_min: int,
    record_size_max: int,
    anchor_count: int,
    min_field_matches: int,
    min_fields: int,
    min_total_matches: int,
    start_limit: int,
    field_hit_limit: int,
    top_records: int,
) -> list[FixedRecordCandidate]:
    position_cache: dict[int, tuple[int, ...]] = {}
    anchors_by_field = {
        field_name: choose_anchors(data, cards, field_name, weights_by_field[field_name], position_cache, anchor_count)
        for field_name in NUMERIC_FIELDS
    }

    hits_by_start_size: dict[tuple[int, int], list[FixedFieldHit]] = defaultdict(list)
    for record_size in range(record_size_min, record_size_max + 1):
        for field_name in NUMERIC_FIELDS:
            anchors = anchors_by_field[field_name]
            if not anchors:
                continue
            for field_offset in range(record_size):
                field_hits = find_fixed_field_hits(
                    data=data,
                    cards=cards,
                    field_name=field_name,
                    record_size=record_size,
                    field_offset=field_offset,
                    value_weights=weights_by_field[field_name],
                    anchors=anchors,
                    min_matches=min_field_matches,
                    start_limit=start_limit,
                    field_hit_limit=field_hit_limit,
                )
                for table_start, hit in field_hits:
                    hits_by_start_size[(table_start, record_size)].append(hit)

    candidates: list[FixedRecordCandidate] = []
    for (table_start, record_size), hits in hits_by_start_size.items():
        selected_hits = select_distinct_field_hits(hits)
        if len(selected_hits) < min_fields:
            continue

        matched_rows = set()
        matched_value_count = 0
        weighted_score = 0.0
        for hit in selected_hits:
            matched_rows.update(hit.matched_rows)
            matched_value_count += hit.match_count
            weighted_score += hit.weighted_score

        if matched_value_count < min_total_matches:
            continue

        score = weighted_score + len(selected_hits) * 12.0 + matched_value_count * 0.2 + len(matched_rows) * 0.15
        surrounding_start, surrounding_bytes = byte_window(data, table_start, context)
        candidates.append(
            FixedRecordCandidate(
                candidate_type="fixed_width_records",
                offset=table_start,
                record_size=record_size,
                field_hits=selected_hits,
                matched_value_count=matched_value_count,
                matched_row_count=len(matched_rows),
                score=score,
                surrounding_start=surrounding_start,
                surrounding_bytes=surrounding_bytes,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.score,
            candidate.matched_value_count,
            candidate.matched_row_count,
            -candidate.record_size,
            -candidate.offset,
        ),
        reverse=True,
    )
    return dedupe_fixed_record_candidates(candidates)[:top_records]


def dedupe_fixed_record_candidates(candidates: list[FixedRecordCandidate]) -> list[FixedRecordCandidate]:
    selected: list[FixedRecordCandidate] = []
    selected_field_sets: list[tuple[int, frozenset[tuple[str, int]]]] = []
    for candidate in candidates:
        field_set = frozenset(
            (hit.field_name, candidate.offset + hit.field_offset) for hit in candidate.field_hits
        )
        if any(
            candidate.record_size == selected_record_size and field_set <= selected_field_set
            for selected_record_size, selected_field_set in selected_field_sets
        ):
            continue
        selected.append(candidate)
        selected_field_sets.append((candidate.record_size, field_set))
    return selected


def longest_ordered_run(data: bytes, cards: list[CardRow], field_name: str, array_start: int) -> int:
    longest = 0
    current = 0
    for card in cards:
        value = card.value_for(field_name)
        if value is None or not 0 <= value <= 0xFF:
            continue
        if data[array_start + card.row_index] == value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def evaluate_array(
    data: bytes,
    cards: list[CardRow],
    field_name: str,
    array_start: int,
    value_weights: dict[int, float],
    context: int,
) -> ParallelArrayCandidate:
    matched_rows: list[int] = []
    weighted_score = 0.0
    for card in cards:
        value = card.value_for(field_name)
        if value is None or not 0 <= value <= 0xFF:
            continue
        if data[array_start + card.row_index] == value:
            matched_rows.append(card.row_index)
            weighted_score += value_weights.get(value, 1.0)

    longest_run = longest_ordered_run(data, cards, field_name, array_start)
    score = weighted_score + len(matched_rows) * 0.25 + longest_run * 2.0
    surrounding_start, surrounding_bytes = byte_window(data, array_start, context)
    return ParallelArrayCandidate(
        candidate_type="parallel_array",
        field_name=field_name,
        offset=array_start,
        match_count=len(matched_rows),
        matched_row_count=len(set(matched_rows)),
        longest_run=longest_run,
        score=score,
        surrounding_start=surrounding_start,
        surrounding_bytes=surrounding_bytes,
        near_fields=[],
    )


def find_parallel_array_candidates(
    data: bytes,
    cards: list[CardRow],
    weights_by_field: dict[str, dict[int, float]],
    context: int,
    anchor_count: int,
    min_matches: int,
    min_run: int,
    start_limit: int,
    near_distance: int,
    top_arrays: int,
) -> list[ParallelArrayCandidate]:
    position_cache: dict[int, tuple[int, ...]] = {}
    candidates: list[ParallelArrayCandidate] = []
    max_start = len(data) - len(cards)

    for field_name in NUMERIC_FIELDS:
        anchors = choose_anchors(data, cards, field_name, weights_by_field[field_name], position_cache, anchor_count)
        start_scores: dict[int, float] = defaultdict(float)
        start_anchor_hits: Counter[int] = Counter()
        for row_index, _value, weight, positions in anchors:
            for position in positions:
                array_start = position - row_index
                if 0 <= array_start <= max_start:
                    start_scores[array_start] += weight
                    start_anchor_hits[array_start] += 1

        ranked_starts = sorted(
            start_scores,
            key=lambda start: (start_anchor_hits[start], start_scores[start], -start),
            reverse=True,
        )[:start_limit]

        for array_start in ranked_starts:
            candidate = evaluate_array(data, cards, field_name, array_start, weights_by_field[field_name], context)
            if candidate.match_count >= min_matches or candidate.longest_run >= min_run:
                candidates.append(candidate)

    candidates_by_field: dict[str, list[ParallelArrayCandidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_field[candidate.field_name].append(candidate)

    for field_candidates in candidates_by_field.values():
        field_candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        del field_candidates[100:]

    bounded_candidates = [candidate for field_candidates in candidates_by_field.values() for candidate in field_candidates]
    for candidate in bounded_candidates:
        near_fields: list[str] = []
        for field_name in NUMERIC_FIELDS:
            if field_name == candidate.field_name:
                continue
            nearby = [
                other
                for other in candidates_by_field.get(field_name, [])
                if abs(other.offset - candidate.offset) <= near_distance
            ]
            if not nearby:
                continue
            best = max(nearby, key=lambda other: other.score)
            distance = best.offset - candidate.offset
            near_fields.append(f"{field_name}@0x{best.offset:06X}({distance:+d})")
        candidate.near_fields = near_fields
        candidate.score += len(near_fields) * 6.0

    bounded_candidates.sort(
        key=lambda candidate: (candidate.score, candidate.match_count, candidate.longest_run, -candidate.offset),
        reverse=True,
    )
    return bounded_candidates[:top_arrays]


def field_hit_summary(hit: FixedFieldHit) -> str:
    return f"{hit.field_name}@{hit.field_offset}:matches={hit.match_count}:score={hit.weighted_score:.3f}"


def write_fixed_candidates(path: Path, candidates: list[FixedRecordCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        fieldnames = [
            "candidate_type",
            "file_offset",
            "bank",
            "cpu_address",
            "record_size",
            "field_offsets",
            "matched_fields",
            "matched_value_count",
            "matched_row_count",
            "score",
            "surrounding_start",
            "surrounding_bytes",
            "notes",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for candidate in candidates:
            address = file_offset_to_gb_addr(candidate.offset)
            writer.writerow(
                {
                    "candidate_type": candidate.candidate_type,
                    "file_offset": f"0x{candidate.offset:06X}",
                    "bank": f"0x{address.bank:02X}",
                    "cpu_address": f"0x{address.cpu_address:04X}",
                    "record_size": candidate.record_size,
                    "field_offsets": ";".join(
                        f"{hit.field_name}:{hit.field_offset}" for hit in candidate.field_hits
                    ),
                    "matched_fields": ";".join(field_hit_summary(hit) for hit in candidate.field_hits),
                    "matched_value_count": candidate.matched_value_count,
                    "matched_row_count": candidate.matched_row_count,
                    "score": f"{candidate.score:.3f}",
                    "surrounding_start": f"0x{candidate.surrounding_start:06X}",
                    "surrounding_bytes": hex_bytes(candidate.surrounding_bytes),
                    "notes": (
                        "candidate only; requires one-byte patch validation in a copied ROM; "
                        "record start alignment is ambiguous until runtime validation"
                    ),
                }
            )


def write_array_candidates(path: Path, candidates: list[ParallelArrayCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        fieldnames = [
            "candidate_type",
            "file_offset",
            "bank",
            "cpu_address",
            "field",
            "matched_fields",
            "matched_value_count",
            "matched_row_count",
            "longest_run",
            "score",
            "near_fields",
            "surrounding_start",
            "surrounding_bytes",
            "notes",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for candidate in candidates:
            address = file_offset_to_gb_addr(candidate.offset)
            writer.writerow(
                {
                    "candidate_type": candidate.candidate_type,
                    "file_offset": f"0x{candidate.offset:06X}",
                    "bank": f"0x{address.bank:02X}",
                    "cpu_address": f"0x{address.cpu_address:04X}",
                    "field": candidate.field_name,
                    "matched_fields": candidate.field_name,
                    "matched_value_count": candidate.match_count,
                    "matched_row_count": candidate.matched_row_count,
                    "longest_run": candidate.longest_run,
                    "score": f"{candidate.score:.3f}",
                    "near_fields": ";".join(candidate.near_fields),
                    "surrounding_start": f"0x{candidate.surrounding_start:06X}",
                    "surrounding_bytes": hex_bytes(candidate.surrounding_bytes),
                    "notes": "candidate only; requires one-byte patch validation in a copied ROM",
                }
            )


def fixed_candidate_to_json(candidate: FixedRecordCandidate) -> dict[str, object]:
    address = file_offset_to_gb_addr(candidate.offset)
    return {
        "candidate_type": candidate.candidate_type,
        "file_offset": candidate.offset,
        "bank": address.bank,
        "cpu_address": address.cpu_address,
        "record_size": candidate.record_size,
        "field_offsets": {hit.field_name: hit.field_offset for hit in candidate.field_hits},
        "matched_fields": [
            {
                "field": hit.field_name,
                "field_offset": hit.field_offset,
                "match_count": hit.match_count,
                "weighted_score": round(hit.weighted_score, 3),
            }
            for hit in candidate.field_hits
        ],
        "matched_value_count": candidate.matched_value_count,
        "matched_row_count": candidate.matched_row_count,
        "score": round(candidate.score, 3),
        "surrounding_start": candidate.surrounding_start,
        "surrounding_bytes": hex_bytes(candidate.surrounding_bytes),
    }


def array_candidate_to_json(candidate: ParallelArrayCandidate) -> dict[str, object]:
    address = file_offset_to_gb_addr(candidate.offset)
    return {
        "candidate_type": candidate.candidate_type,
        "file_offset": candidate.offset,
        "bank": address.bank,
        "cpu_address": address.cpu_address,
        "field": candidate.field_name,
        "matched_value_count": candidate.match_count,
        "matched_row_count": candidate.matched_row_count,
        "longest_run": candidate.longest_run,
        "score": round(candidate.score, 3),
        "near_fields": candidate.near_fields,
        "surrounding_start": candidate.surrounding_start,
        "surrounding_bytes": hex_bytes(candidate.surrounding_bytes),
    }


def write_json(path: Path, records: list[FixedRecordCandidate], arrays: list[ParallelArrayCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fixed_width_records": [fixed_candidate_to_json(candidate) for candidate in records],
        "parallel_arrays": [array_candidate_to_json(candidate) for candidate in arrays],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def print_fixed_candidate(candidate: FixedRecordCandidate) -> None:
    address = file_offset_to_gb_addr(candidate.offset)
    field_offsets = ", ".join(f"{hit.field_name}@{hit.field_offset}" for hit in candidate.field_hits)
    print(
        f"fixed_width_records offset=0x{candidate.offset:06X} "
        f"bank=0x{address.bank:02X} cpu=0x{address.cpu_address:04X} "
        f"record_size={candidate.record_size} fields={field_offsets} "
        f"matches={candidate.matched_value_count} rows={candidate.matched_row_count} "
        f"score={candidate.score:.3f}"
    )
    print(f"  surrounding @ 0x{candidate.surrounding_start:06X}: {hex_bytes(candidate.surrounding_bytes)}")


def print_array_candidate(candidate: ParallelArrayCandidate) -> None:
    address = file_offset_to_gb_addr(candidate.offset)
    print(
        f"parallel_array offset=0x{candidate.offset:06X} "
        f"bank=0x{address.bank:02X} cpu=0x{address.cpu_address:04X} "
        f"field={candidate.field_name} matches={candidate.match_count} "
        f"rows={candidate.matched_row_count} longest_run={candidate.longest_run} "
        f"score={candidate.score:.3f} near={';'.join(candidate.near_fields) or '-'}"
    )
    print(f"  surrounding @ 0x{candidate.surrounding_start:06X}: {hex_bytes(candidate.surrounding_bytes)}")


def main() -> int:
    args = parse_args()
    if args.record_size_min < 1 or args.record_size_max < args.record_size_min:
        print("error: record size range is invalid", file=sys.stderr)
        return 1
    if args.top_records < 0 or args.top_arrays < 0 or args.print_limit < 0:
        print("error: top/print limits must be non-negative", file=sys.stderr)
        return 1

    try:
        data = read_rom(args.rom)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    cards, warnings = load_cards(args.known_cards)
    print(f"Loaded ROM: {args.rom} ({len(data)} bytes)")
    print(f"Card CSV: {args.known_cards}")
    print(f"Visible card rows loaded: {len(cards)}")
    for field_name in NUMERIC_FIELDS:
        print(f"Numeric {field_name} values: {len(numeric_values(cards, field_name))}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if not cards:
        write_fixed_candidates(args.record_output, [])
        write_array_candidates(args.array_output, [])
        write_json(args.json_output, [], [])
        print("No card rows available for scanning.")
        return 2

    weights_by_field = build_value_weights(cards)
    fixed_candidates = find_fixed_record_candidates(
        data=data,
        cards=cards,
        weights_by_field=weights_by_field,
        context=args.context,
        record_size_min=args.record_size_min,
        record_size_max=args.record_size_max,
        anchor_count=args.anchor_count,
        min_field_matches=args.min_record_field_matches,
        min_fields=args.min_record_fields,
        min_total_matches=args.min_record_total_matches,
        start_limit=args.start_limit,
        field_hit_limit=args.field_hit_limit,
        top_records=args.top_records,
    )
    array_candidates = find_parallel_array_candidates(
        data=data,
        cards=cards,
        weights_by_field=weights_by_field,
        context=args.context,
        anchor_count=args.anchor_count,
        min_matches=args.min_array_matches,
        min_run=args.min_array_run,
        start_limit=args.start_limit,
        near_distance=args.near_distance,
        top_arrays=args.top_arrays,
    )

    write_fixed_candidates(args.record_output, fixed_candidates)
    write_array_candidates(args.array_output, array_candidates)
    write_json(args.json_output, fixed_candidates, array_candidates)

    print(f"Fixed-width record candidates exported: {len(fixed_candidates)} -> {args.record_output}")
    print(f"Parallel-array candidates exported: {len(array_candidates)} -> {args.array_output}")
    print(f"Combined JSON exported: {args.json_output}")

    if fixed_candidates:
        print()
        print("Top fixed-width record candidates:")
        for candidate in fixed_candidates[: args.print_limit]:
            print_fixed_candidate(candidate)
    else:
        print("No fixed-width record candidates met the thresholds.")

    if array_candidates:
        print()
        print("Top parallel-array candidates:")
        for candidate in array_candidates[: args.print_limit]:
            print_array_candidate(candidate)
    else:
        print("No parallel-array candidates met the thresholds.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
