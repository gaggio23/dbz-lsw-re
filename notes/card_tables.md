# Card Tables

## Candidate Offsets

Candidate offsets are promoted only after copied-ROM patch tests. `tools/scan_card_tables.py` reports search candidates; scanner output alone is not table identification.

| Offset | Bank | CPU Address | Evidence | Status |
| --- | --- | --- | --- | --- |
| `0x044315` | `0x11` | `0x4315` | Fixed-width scan candidate: record size `16`, field offsets `atk=12`, `acc=13`, `cc=15`; `299` matched numeric values across `125` rows; score `1165.544`. One `cc` mismatch remains for card 102 (`Ene.Absorber`), where CSV says `9` and the candidate byte is `8`. Patch validation changed card 13 (`S.Kamehameha`) `cc` from `23` to `22`, card 89 (`Guru`) `cc` from `6` to `5`, card 89 (`Guru`) `acc` from `100` to `95`, and card 13 (`S.Kamehameha`) `atk` from `30` to `31`. | Numeric visible fields `atk`, `acc`, and `cc` are patch-validated for this fixed-width layout. Type/category, nonnumeric effects, and the card 102 `cc` mismatch still need investigation. |

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

Validated observations:

- Card 13 (`S.Kamehameha`) `cc`: original ROM shows `23`; patched ROM `patched/baserom_patch_0443E4_16.gbc` shows `22`. Patched byte was file offset `0x0443E4`, bank `0x11`, CPU `0x43E4`, old byte `0x17`, new byte `0x16`, SHA1 `7c49ed7887f985b61a3b050066cd476e51d3c94c`, SHA256 `c5e69ec8529480418f3ad5f24020c17cceb4a3a34abfbf10d1681780b880f20b`.
- Card 89 (`Guru`) `cc`: original ROM shows `6`; patched ROM `patched/baserom_patch_0448A4_05.gbc` shows `5`. Patched byte was file offset `0x0448A4`, bank `0x11`, CPU `0x48A4`, old byte `0x06`, new byte `0x05`, SHA1 `84561fe85c82dc85485cb337acce20f09cccaf7e`, SHA256 `8642153bdf52e903a06a304d60f25250ec54909cab15776436592074f86935d6`.
- Card 89 (`Guru`) `acc`: original ROM shows `100`; patched ROM `patched/baserom_patch_0448A2_5F.gbc` shows `95`. Patched byte was file offset `0x0448A2`, bank `0x11`, CPU `0x48A2`, old byte `0x64`, new byte `0x5F`, SHA1 `d3c0177a13be04dc56d0e9176f31f15ef89a789b`, SHA256 `b9fde1064c5e0d3361708bf545d30e8eb20e851a9fd02c5de829d9042a312655`.
- Card 13 (`S.Kamehameha`) `atk`: original ROM shows `30`; patched ROM `patched/baserom_patch_0443E1_1F.gbc` shows `31`. Patched byte was file offset `0x0443E1`, bank `0x11`, CPU `0x43E1`, old byte `0x1E`, new byte `0x1F`, SHA1 `cdf648a74adec38a984bae7df62990107a067f13`, SHA256 `273ef469bb2010072dc857e00e342949b53c2648a637a50a335f38e99b108cd7`.

## BGB Candidate Validation Workflow

1. Use BGB read/watch breakpoints on the validated field bytes while opening the card UI. For switchable ROM banks, make sure bank `0x11` is mapped at `$4000-$7FFF` before trusting CPU addresses.
2. Investigate the remaining card 102 (`Ene.Absorber`) `cc` mismatch: CSV says `9`, but the candidate byte is `8`.
3. Identify neighboring record bytes for type/category, rarity, nonnumeric effects, and card IDs. Do not assume their meaning until patch tests or runtime reads confirm them.
4. After runtime reads confirm the game uses this record block, promote the layout from patch-validated numeric fields to a fully documented ROM table.
