# dbz-lsw-re

Reverse-engineering workspace for the Game Boy Color game **Dragon Ball Z: Legendary Super Warriors**.

The project goal is to build a reproducible, text-based record of the game's mechanics: card data, card numerical effects, candidate ROM table locations, and eventually character statistics. The repo intentionally avoids storing copyrighted ROM data. Local ROMs, patched ROMs, saves, emulator states, and binary dumps are ignored and must stay private.

## Current Scope

The current work focuses on the 125 battle cards:

- card number and visible order
- card name
- card category/type
- CC cost
- attack/power value where numeric
- accuracy where finite
- rarity
- effect text and source notes

The scanner uses this CSV to look for candidate ROM layouts. A candidate is not considered verified until a copied ROM is patched and the expected in-game UI change is observed in an emulator/debugger such as BGB.

Character statistics are part of the project purpose, but they have not been extracted into a verified data file yet. When added, they should follow the same rules: small text/CSV/JSON source files, conservative candidate scans, and emulator validation before claiming a ROM location is real.

## Repository Layout

```text
.
├── Makefile
├── README.md
├── data/
│   ├── candidates/
│   │   ├── card_parallel_array_candidates.csv
│   │   ├── card_table_candidates.csv
│   │   └── card_table_candidates.json
│   └── raw/
│       └── known_cards_manual.csv
├── notes/
│   ├── card_tables.md
│   ├── feint_precision.md
│   └── methodology.md
└── tools/
    ├── common.py
    ├── import_strategywiki_cards.py
    ├── patch_card_value.py
    ├── rom_info.py
    └── scan_card_tables.py
```

## Data Files

[data/raw/known_cards_manual.csv](data/raw/known_cards_manual.csv) is the main card dataset. It contains one row per visible card, in card order.

Columns:

```csv
card_number,card_name,type,cc,atk,acc,rarity,notes
```

Field meaning:

- `card_number`: visible card number, `1..125`
- `card_name`: visible card name
- `type`: normalized category: `command`, `damage`, `beam`, `support`, `defense`, or `special`
- `cc`: visible CC cost
- `atk`: numeric attack/power value, or `--` when the card has no numeric power value
- `acc`: numeric accuracy, or `--` when the card has no finite accuracy value
- `rarity`: star count, `1..3`
- `notes`: source details, aliases, effect text, and related metadata

[data/candidates/card_table_candidates.csv](data/candidates/card_table_candidates.csv) contains fixed-width record candidates emitted by the scanner. These rows are evidence only, not verified ROM tables.

[data/candidates/card_parallel_array_candidates.csv](data/candidates/card_parallel_array_candidates.csv) contains parallel-array candidates emitted by the scanner. It may contain only a header if no candidate meets the conservative thresholds.

[data/candidates/card_table_candidates.json](data/candidates/card_table_candidates.json) is the optional machine-readable combined export for fixed-width and parallel-array scan results.

## Notes

[notes/methodology.md](notes/methodology.md) defines the project rules: no ROM commits, no unsupported conclusions, and emulator validation before promoting candidates.

[notes/card_tables.md](notes/card_tables.md) documents the card CSV schema, scanner assumptions, current candidate offsets, and the BGB validation workflow.

[notes/feint_precision.md](notes/feint_precision.md) stores focused notes for the `Feint` card and precision-related behavior.

## Tools

[tools/common.py](tools/common.py) contains shared helpers for reading local ROMs, hashing data, and converting file offsets to Game Boy bank/CPU addresses using a simple 16 KiB bank mapping.

[tools/rom_info.py](tools/rom_info.py) prints local ROM metadata and hashes. Example:

```sh
make rom-info
```

[tools/import_strategywiki_cards.py](tools/import_strategywiki_cards.py) imports the StrategyWiki card table into the raw card CSV. It preserves source information in `notes`. The imported data is lookup/transcription data and still requires emulator validation before it can be treated as ROM evidence.

```sh
make import-strategywiki-cards
```

[tools/scan_card_tables.py](tools/scan_card_tables.py) scans the private local ROM for candidate card numeric data locations.

It supports two search modes:

- fixed-width records, trying record sizes from `3` to `32` bytes
- parallel arrays, searching visible-order byte arrays for `cc`, `atk`, and `acc`

The scanner scores candidates by exact matches, matched rows, field consistency, and penalties for low-information values such as `0`, `1`, `2`, and `10`. It exports only top candidates and caps surrounding byte windows at 32 bytes.

```sh
make scan-card-tables
```

[tools/patch_card_value.py](tools/patch_card_value.py) patches exactly one byte in a copied ROM under `patched/`. It refuses to overwrite the original ROM and prints the old value, new value, SHA1, and SHA256 of the patched ROM.

Example for the current recommended validation card, `S.Kamehameha` card 13:

```sh
python3 tools/patch_card_value.py baserom.gbc 0x0443E4 0x16
```

This changes the current candidate byte for card 13 `cc` from `23` to `22` in a copied ROM. If the candidate is correct, the patched ROM should show `S.Kamehameha` with CC `22` instead of `23`.

## Make Targets

```sh
make rom-info
make scan-card-tables
make import-strategywiki-cards
make patch-byte-example PATCH_OFFSET=0x0443E4 PATCH_VALUE=0x16
make clean
```

`ROM` defaults to `baserom.gbc`:

```sh
make scan-card-tables ROM=/path/to/private/local/rom.gbc
```

## Current Candidate State

The latest scanner run found one deduplicated fixed-width candidate family and no parallel-array candidates meeting the current thresholds.

Top candidate:

```text
candidate_type: fixed_width_records
file_offset: 0x044315
bank: 0x11
cpu_address: 0x4315
record_size: 16
field_offsets: atk=12, acc=13, cc=15
matched_value_count: 299
matched_row_count: 125
score: 1165.544
```

This is not verified. It is a strong candidate because many visible numeric card values line up at consistent offsets, but only BGB/runtime patch validation can prove the game uses these bytes.

## Recommended Validation Step

Use a card that is already available in the save state. Current recommendation:

- card: `S.Kamehameha`
- card number: `13`
- field: `cc`
- visible old value: `23`
- test new value: `22`
- candidate file offset: `0x0443E4`
- candidate bank/CPU address: bank `0x11`, CPU `0x43E4`

Create the patched ROM:

```sh
python3 tools/patch_card_value.py baserom.gbc 0x0443E4 0x16
```

Then compare in BGB:

1. Load the original ROM and confirm card 13 shows CC `23`.
2. Load the patched ROM from `patched/`.
3. Open the same card UI and check whether only card 13's CC changes to `22`.
4. If it does not change, the candidate is not verified.
5. If it changes, test another field or adjacent card before promoting the layout to verified.

## Data Safety

Do not commit:

- ROMs: `*.gb`, `*.gbc`
- patched ROMs
- saves or emulator states
- binary dumps or RAM captures
- large copyrighted byte excerpts

The `.gitignore` already excludes these local/private artifacts.
