#!/usr/bin/env python3
"""Print basic metadata from a Game Boy / Game Boy Color ROM header."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import read_rom, sha1, sha256


ROM_SIZE_DESCRIPTIONS = {
    0x00: "32 KiB / 2 banks",
    0x01: "64 KiB / 4 banks",
    0x02: "128 KiB / 8 banks",
    0x03: "256 KiB / 16 banks",
    0x04: "512 KiB / 32 banks",
    0x05: "1 MiB / 64 banks",
    0x06: "2 MiB / 128 banks",
    0x07: "4 MiB / 256 banks",
    0x08: "8 MiB / 512 banks",
    0x52: "1.1 MiB / 72 banks",
    0x53: "1.2 MiB / 80 banks",
    0x54: "1.5 MiB / 96 banks",
}

RAM_SIZE_DESCRIPTIONS = {
    0x00: "No RAM",
    0x01: "2 KiB",
    0x02: "8 KiB",
    0x03: "32 KiB / 4 banks",
    0x04: "128 KiB / 16 banks",
    0x05: "64 KiB / 8 banks",
}


def decode_title(raw_title: bytes) -> str:
    title = raw_title.split(b"\0", 1)[0]
    return title.decode("ascii", errors="replace").strip()


def header_checksum(data: bytes) -> int:
    checksum = 0
    for byte in data[0x0134:0x014D]:
        checksum = (checksum - byte - 1) & 0xFF
    return checksum


def global_checksum(data: bytes) -> int:
    total = 0
    for index, byte in enumerate(data):
        if index in (0x014E, 0x014F):
            continue
        total = (total + byte) & 0xFFFF
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", default="baserom.gbc", help="ROM path, default: baserom.gbc")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rom_path = Path(args.rom)

    try:
        data = read_rom(rom_path)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if len(data) < 0x0150:
        print(f"error: ROM is too small to contain a complete Game Boy header: {rom_path}", file=sys.stderr)
        return 1

    title = decode_title(data[0x0134:0x0144])
    cgb_flag = data[0x0143]
    cartridge_type = data[0x0147]
    rom_size = data[0x0148]
    ram_size = data[0x0149]
    destination_code = data[0x014A]
    old_licensee_code = data[0x014B]
    version = data[0x014C]
    stored_header_checksum = data[0x014D]
    stored_global_checksum = int.from_bytes(data[0x014E:0x0150], byteorder="big")

    file_size = len(data)
    bank_count = (file_size + 0x3FFF) // 0x4000
    computed_header_checksum = header_checksum(data)
    computed_global_checksum = global_checksum(data)

    print(f"Path: {rom_path}")
    print(f"File size: {file_size} bytes")
    print(f"16 KiB banks: {bank_count}")
    print(f"SHA1: {sha1(data)}")
    print(f"SHA256: {sha256(data)}")
    print()
    print("Header:")
    print(f"  Title: {title}")
    print(f"  CGB flag: 0x{cgb_flag:02X}")
    print(f"  Cartridge type: 0x{cartridge_type:02X}")
    print(f"  ROM size: 0x{rom_size:02X} ({ROM_SIZE_DESCRIPTIONS.get(rom_size, 'unknown')})")
    print(f"  RAM size: 0x{ram_size:02X} ({RAM_SIZE_DESCRIPTIONS.get(ram_size, 'unknown')})")
    print(f"  Destination code: 0x{destination_code:02X}")
    print(f"  Old licensee code: 0x{old_licensee_code:02X}")
    print(f"  Version: 0x{version:02X}")
    print(
        "  Header checksum: "
        f"0x{stored_header_checksum:02X} "
        f"(computed 0x{computed_header_checksum:02X}, "
        f"{'ok' if stored_header_checksum == computed_header_checksum else 'mismatch'})"
    )
    print(
        "  Global checksum: "
        f"0x{stored_global_checksum:04X} "
        f"(computed 0x{computed_global_checksum:04X}, "
        f"{'ok' if stored_global_checksum == computed_global_checksum else 'mismatch'})"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
