# Methodology

This project treats the local ROM as private copyrighted input. ROM bytes, binary dumps, patched ROMs, saves, emulator states, and raw RAM captures must not be committed.

## Source Of Truth

The source of truth is emulator validation plus disassembly. Static pattern matches are only candidates until runtime behavior confirms them.

Every discovered offset needs:

- file offset
- ROM bank and CPU address
- reason it was selected
- emulator trace or watchpoint evidence
- a validation note explaining what reads or writes it

## Workflow

1. Inspect static tables first because they are easier to locate, compare, and validate.
2. Record candidate offsets in `notes/` or `data/candidates/` with assumptions clearly marked.
3. Validate candidates in BGB or another debugger before moving anything to `data/verified/`.
4. Study algorithms only after related data tables have plausible validated anchors.

## Data Handling

Do not commit ROM contents or large binary excerpts. Prefer small text notes, CSV, JSON, and scripts that reproduce analysis locally from `baserom.gbc`.
