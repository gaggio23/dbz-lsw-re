# Card Tables

## Candidate Offsets

No candidate offsets have been validated yet. `tools/scan_card_tables.py` reports search candidates only; do not treat its output as a table identification without emulator validation and a copied-ROM patch test.

| Offset | Bank | CPU Address | Evidence | Status |
| --- | --- | --- | --- | --- |
| `0x044315` | `0x11` | `0x4315` | Fixed-width scan candidate: record size `16`, field offsets `atk=12`, `acc=13`, `cc=15`; `299` matched numeric values across `125` rows; score `1165.544`. One `cc` mismatch remains for card 102 (`Ene.Absorber`), where CSV says `9` and the candidate byte is `8`. | Candidate only; record-start alignment is ambiguous until BGB patch validation. |

## Known Visible Card Stats

Use `data/raw/known_cards_manual.csv` for stats observed in-game or from trusted manual transcription. Do not treat them as ROM table evidence until they are traced back to reads from ROM.

| Card | Visible Stat | Value | Source | Notes |
| --- | --- | --- | --- | --- |

The CSV columns are:

| Column | Meaning |
| --- | --- |
| `card_number` | Integer card number from `1` to `125`. |
| `card_name` | Card name as shown in the game UI or card image. Names are variable-length strings and may contain spaces. |
| `type` | Lowercase card type enum: `command`, `damage`, `beam`, `support`, `defense`, or `special`. StrategyWiki `Item` rows are normalized to `support`; StrategyWiki `Avoid` rows are normalized to `defense`. |
| `cc` | Visible card cost as an integer from `0` to `33`. Command cards may use `0`. |
| `atk` | Visible attack/power value as a non-negative integer, or `--` when the card has no numeric power value. Non-numeric StrategyWiki power/effect text is preserved in `notes`. |
| `acc` | Visible accuracy as an integer multiple of `5` from `20` to `100`, or `--` when the card image shows no accuracy value. Treat `--` as infinite precision. |
| `rarity` | Numeric rarity star count from `1` to `3`; more stars means rarer. This is the value shown after `R.` in card images. |
| `notes` | Manual source details, such as screen, deck, save state, language, or uncertainty. |

Rows in this file may come from the game UI or a trusted guide transcription. Treat guide imports as lookup data only; they are not ROM table evidence until emulator validation traces them back to ROM reads. Placeholder or guessed values should be left blank or clearly marked in `notes` and will not be useful for candidate discovery.

## Candidate Scanner

Run:

```sh
python3 tools/scan_card_tables.py baserom.gbc
```

The scanner loads `data/raw/known_cards_manual.csv`, strips whitespace, treats blank cells and `--` as missing numeric values, preserves visible card order through a stable `row_index` from `card_number - 1`, and scans only byte-sized numeric values from `cc`, `atk`, and `acc`.

Scanner assumptions:

- The CSV used by the current run is `data/raw/known_cards_manual.csv` with columns `card_number,card_name,type,cc,atk,acc,rarity,notes`.
- Current row count is `125`, with stable row indexes `0..124`.
- Numeric field counts are `cc=125`, `atk=63`, and `acc=112`.
- Type/category is not searched yet because no ROM numeric encoding for `command`, `damage`, `beam`, `support`, `defense`, or `special` has been validated.
- Mode A tests fixed-width records with record sizes from `3` to `32` bytes and scores consistent field offsets inside each record.
- Mode B tests parallel byte arrays for each numeric field in visible order and reports nearby arrays.
- Common values such as `0`, `1`, `2`, and `10` receive low-information penalties.
- Surrounding byte windows in candidate outputs are capped at `32` bytes.

Outputs:

- `data/candidates/card_table_candidates.csv` for fixed-width record candidates.
- `data/candidates/card_parallel_array_candidates.csv` for parallel-array candidates.
- `data/candidates/card_table_candidates.json` for optional combined machine-readable output.

Latest scan result:

- Fixed-width records: one deduplicated candidate family exported.
- Parallel arrays: no candidates met the current conservative thresholds.
- Top fixed-width candidate: `0x044315`, bank `0x11`, CPU `0x4315`, record size `16`, field offsets `atk=12`, `acc=13`, `cc=15`, matched value count `299`, matched row count `125`, score `1165.544`.
- Top candidate surrounding window at `0x044305`: `10 00 05 00 00 00 00 00 00 00 00 04 00 00 B1 00 00 00 00 00 00 00 00 00 00 00 00 01 00 64 2F 00`.

## StrategyWiki Import

`tools/import_strategywiki_cards.py` imports the StrategyWiki card table into `data/raw/known_cards_manual.csv`:

```sh
python3 tools/import_strategywiki_cards.py
```

The importer uses the StrategyWiki Cards page as its source: <https://strategywiki.org/wiki/Dragon_Ball_Z:_Legendary_Super_Warriors/Cards>. StrategyWiki content is published under Creative Commons Attribution-ShareAlike 4.0; keep attribution and source notes when using imported data.

The scanner is intentionally conservative. A candidate means only that nearby bytes match visible numeric card values under one possible layout model.

## Validation Notes

Record emulator watchpoints, breakpoints, traces, and disassembly references here. Each validated offset should explain how the game uses the data at runtime.

## BGB Candidate Validation Workflow

1. Create a one-byte patched copy for a card that is visible in the current save state. Current recommended test: patch card 13 (`S.Kamehameha`) `cc` from `23` to `22` at file offset `0x0443E4`:

```sh
python3 tools/patch_card_value.py baserom.gbc 0x0443E4 0x16
```

2. Load the original ROM in BGB, view card 13, and record the visible `cc` value.
3. Load the patched ROM from `patched/`, view card 13 at the same UI screen, and check whether only the expected visible `cc` value changes from `23` to `22`.
4. If the UI does not change, the candidate is not verified. If it changes as expected, test at least one more field and one adjacent card before treating the fixed width or field offsets as validated.
5. In BGB, use bank `0x11` and CPU address `0x43E4` for the patch byte when setting read/watch breakpoints. For switchable ROM banks, make sure bank `0x11` is mapped at `$4000-$7FFF` before trusting the CPU address.
6. Record the emulator evidence, patched offset, old/new byte values, patched ROM hashes, and observed UI behavior before promoting any candidate from candidate-only status.
