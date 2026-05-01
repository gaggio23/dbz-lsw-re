# Save Editing

## SRAM Card Count Array

Two 8 KiB SRAM saves were compared:

- `local_saves/original/dbzlsw_before_22.srm`: story 22, 150 total cards.
- `local_saves/original/dbzlsw_after_23.srm`: after winning story 22 vs Kid Trunks, 151 total cards.

The reward card was card 37 (`Flash Punch`), changing from 0 copies to 1 copy.

The only 125-byte window matching the known inventory change is:

| Field | Value |
| --- | --- |
| Card count array start | `0x037E` |
| Card count array end | `0x03FA` |
| Card index formula | `offset = 0x037E + card_number - 1` |
| Before total | `150` |
| After total | `151` |
| Flash Punch card number | `37` |
| Flash Punch offset | `0x03A2` |
| Flash Punch before/after | `0 -> 1` |

Card 94 (`Dabura`) is at offset `0x03DB`.

## Patch Tool

Use `tools/patch_save_card_count.py` to patch a copied SRAM save under `local_saves/patched/`.

Example: set Dabura to 3 copies in the post-story-22 save:

```sh
python3 tools/patch_save_card_count.py local_saves/original/dbzlsw_after_23.srm 94 3
```

The tool patches only the card-count byte and does not update any checksum bytes. If BGB or the game rejects the save, the next step is to identify checksum bytes by comparing more controlled save pairs.
