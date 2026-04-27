"""Shared helpers for local ROM inspection tools."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple


class GBAddress(NamedTuple):
    bank: int
    bank_local_offset: int
    cpu_address: int


def read_rom(path: str | Path) -> bytes:
    """Read a ROM file into memory, raising a clean FileNotFoundError if absent."""
    rom_path = Path(path)
    if not rom_path.exists():
        raise FileNotFoundError(f"ROM not found: {rom_path}")
    if not rom_path.is_file():
        raise IsADirectoryError(f"ROM path is not a file: {rom_path}")
    return rom_path.read_bytes()


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_offset_to_gb_addr(offset: int) -> GBAddress:
    """Map a file offset to a simple 16 KiB Game Boy ROM bank CPU address."""
    if offset < 0:
        raise ValueError("offset must be non-negative")

    bank_size = 0x4000
    bank = offset // bank_size
    bank_local_offset = offset % bank_size
    cpu_address = bank_local_offset if bank == 0 else 0x4000 + bank_local_offset
    return GBAddress(bank=bank, bank_local_offset=bank_local_offset, cpu_address=cpu_address)
