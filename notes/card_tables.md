# Card Tables

## Candidate Offsets

No candidate offsets have been validated yet. `tools/scan_card_tables.py` reports search candidates only; do not treat its output as a table identification without emulator validation.

| Offset | Bank | CPU Address | Evidence | Status |
| --- | --- | --- | --- | --- |

## Known Visible Card Stats

Use `data/raw/known_cards_manual.csv` for stats observed in-game or from trusted manual transcription. Do not treat them as ROM table evidence until they are traced back to reads from ROM.

| Card | Visible Stat | Value | Source | Notes |
| --- | --- | --- | --- | --- |

The CSV columns are:

| Column | Meaning |
| --- | --- |
| `card_number` | Integer card number from `1` to `125`. |
| `card_name` | Card name as shown in the game UI or card image. Names are variable-length strings and may contain spaces. |
| `type` | Lowercase card type enum: `command`, `damage`, `beam`, `support`, or `defense`. |
| `cc` | Visible card cost as an integer from `0` to `33`. Command cards may use `0`. |
| `atk` | Visible attack value as a non-negative integer. |
| `acc` | Visible accuracy as an integer multiple of `5` from `20` to `100`, or `--` when the card image shows no accuracy value. Treat `--` as infinite precision. |
| `rarity` | Numeric rarity star count from `1` to `3`; more stars means rarer. This is the value shown after `R.` in card images. |
| `notes` | Manual source details, such as screen, deck, save state, language, or uncertainty. |

Rows in this file must be manually verified from the game UI before use. Placeholder or guessed values should be left blank or clearly marked in `notes` and will not be useful for candidate discovery.

## Candidate Scanner

Run:

```sh
python3 tools/scan_card_tables.py baserom.gbc
```

The scanner loads `data/raw/known_cards_manual.csv`, validates the schema constraints above, keeps only rows where `cc`, `atk`, and `acc` are numeric, and searches for compact byte patterns involving those values. Rows with `acc` set to `--` are valid card data, but they are skipped by the current candidate scanner because there is no finite accuracy byte pattern to search for. It tries all visible field orders and allows small unknown gaps between fields because records may include type, flags, IDs, or padding between visible stats. Candidate output is written to `data/candidates/card_table_candidates.csv`.

The scanner is intentionally conservative. A candidate means only that nearby bytes match one manually observed card's visible values under one possible encoding/order/gap model.

## Validation Notes

Record emulator watchpoints, breakpoints, traces, and disassembly references here. Each validated offset should explain how the game uses the data at runtime.

## BGB Candidate Validation Workflow

1. Add several manually verified card rows to `data/raw/known_cards_manual.csv`. Prefer cards with distinctive combinations of `cc`, `atk`, and `acc`; repeated common values produce many false candidates.
2. Run `python3 tools/scan_card_tables.py baserom.gbc`.
3. Open the candidate CSV and group offsets that are close together, share the same field order, or appear in the same ROM bank.
4. In BGB, load the ROM and reach a screen that displays one of the recorded cards.
5. Use the candidate row's ROM bank and CPU address to inspect the bytes in BGB's debugger/memory viewer. For switchable ROM banks, make sure the candidate bank is currently mapped at `$4000-$7FFF` before trusting the CPU address.
6. Set breakpoints or read watchpoints around the candidate CPU address while opening or refreshing the card UI. Record whether the game reads those bytes when the visible card stats are drawn or copied into RAM.
7. If a candidate appears active, test neighboring records by checking whether adjacent bytes correspond to nearby cards in the UI/card list. Do not assume fixed width until multiple adjacent records validate with consistent spacing.
8. Promote an offset to the table above only after recording the BGB evidence, the visible card values used, the bank/address, and the inferred record width or layout uncertainty.
