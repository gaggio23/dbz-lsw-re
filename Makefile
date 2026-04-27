.PHONY: rom-info scan-card-tables clean

ROM ?= baserom.gbc

rom-info:
	python3 tools/rom_info.py $(ROM)

scan-card-tables:
	python3 tools/scan_card_tables.py $(ROM)

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
