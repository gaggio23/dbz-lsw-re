#!/usr/bin/env python3
"""Import StrategyWiki card-table data into the manual card CSV."""

from __future__ import annotations

import argparse
import csv
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


SOURCE_URL = "https://strategywiki.org/wiki/Dragon_Ball_Z:_Legendary_Super_Warriors/Cards"
DEFAULT_OUTPUT = Path("data/raw/known_cards_manual.csv")
CSV_FIELDS = ["card_number", "card_name", "type", "cc", "atk", "acc", "rarity", "notes"]
TYPE_MAP = {
    "Command": "command",
    "Damage": "damage",
    "Beam": "beam",
    "Item": "support",
    "Avoid": "defense",
    "Special": "special",
}


class WikiTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_target_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and "wikitable" in (attributes.get("class") or ""):
            self.in_target_table = True
            self.table_depth = 1
        elif self.in_target_table and tag == "table":
            self.table_depth += 1

        if not self.in_target_table:
            return

        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.current_cell = []
        elif tag == "br" and self.in_cell:
            self.current_cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_target_table:
            return

        if tag in {"td", "th"} and self.in_cell:
            self.current_row.append(clean_cell_text("".join(self.current_cell)))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            self.rows.append(self.current_row)
            self.in_row = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_target_table = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)


def clean_cell_text(raw_text: str) -> str:
    lines = [" ".join(line.split()) for line in raw_text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        default=SOURCE_URL,
        help=f"StrategyWiki HTML file or URL, default: {SOURCE_URL}",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help=f"CSV output path, default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def read_source(source: str) -> str:
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    return Path(source).read_text(encoding="utf-8", errors="replace")


def parse_card_rows(html: str) -> list[list[str]]:
    parser = WikiTableParser()
    parser.feed(html)
    return [row for row in parser.rows if len(row) == 9 and row[0].strip().isdigit()]


def build_notes(name_cell: str, source_type: str, power_effect: str, gs_code: str) -> str:
    parts = ["source=StrategyWiki Cards"]
    name_lines = name_cell.splitlines()
    if len(name_lines) > 1:
        alias = name_lines[1].strip()
        if alias.startswith("(") and alias.endswith(")"):
            alias = alias[1:-1]
        parts.append(f"alias={alias}")
    parts.append(f"source_type={source_type}")
    parts.append(f"power_effect={power_effect}")
    parts.append(f"gs_code={gs_code}")
    return "; ".join(parts)


def normalize_card(row: list[str]) -> dict[str, str]:
    card_number, _image, name_cell, rarity, source_type, power_effect, acc, cc, gs_code = row
    card_type = TYPE_MAP[source_type]
    normalized_power = " ".join(power_effect.split())
    atk = normalized_power if normalized_power.isdigit() else "--"
    card_name = name_cell.splitlines()[0]

    return {
        "card_number": str(int(card_number)),
        "card_name": card_name,
        "type": card_type,
        "cc": str(int(cc)),
        "atk": atk,
        "acc": acc,
        "rarity": str(len(rarity)),
        "notes": build_notes(name_cell, source_type, normalized_power, gs_code),
    }


def write_cards(path: Path, cards: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(cards)


def main() -> int:
    args = parse_args()
    try:
        html = read_source(args.source)
        rows = parse_card_rows(html)
        cards = [normalize_card(row) for row in rows]
    except (KeyError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if len(cards) != 125:
        print(f"error: expected 125 card rows, found {len(cards)}", file=sys.stderr)
        return 1

    write_cards(args.output, cards)
    print(f"Wrote {len(cards)} cards to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
