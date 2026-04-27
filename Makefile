.PHONY: rom-info scan-card-tables import-strategywiki-cards patch-byte-example clean

ROM ?= baserom.gbc
PATCH_OFFSET ?= 0x0000
PATCH_VALUE ?= 0x00

rom-info:
	python3 tools/rom_info.py $(ROM)

scan-card-tables:
	python3 tools/scan_card_tables.py $(ROM)

import-strategywiki-cards:
	python3 tools/import_strategywiki_cards.py

patch-byte-example:
	python3 tools/patch_card_value.py $(ROM) $(PATCH_OFFSET) $(PATCH_VALUE)

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
