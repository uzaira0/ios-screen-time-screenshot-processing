#!/usr/bin/env python3
"""Check that the TypeScript RustProcessingResult interface matches the Rust ProcessingResult struct.

Parses both files with regex and compares field names. Exits non-zero if they differ.

Usage:
    python scripts/check-tauri-contract.py         # check
    python scripts/check-tauri-contract.py --fix    # show what to fix
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

RUST_FILE = ROOT / "crates" / "processing" / "src" / "types.rs"
TS_FILE = ROOT / "frontend" / "src" / "core" / "implementations" / "tauri" / "TauriProcessingService.ts"


def extract_rust_fields() -> set[str]:
    """Extract field names from Rust ProcessingResult struct."""
    content = RUST_FILE.read_text()
    # Find the struct block
    match = re.search(r"pub struct ProcessingResult\s*\{(.*?)\}", content, re.DOTALL)
    if not match:
        print(f"ERROR: Could not find ProcessingResult struct in {RUST_FILE}")
        sys.exit(2)

    fields = set()
    for line in match.group(1).split("\n"):
        # Match: pub field_name: Type,
        m = re.match(r"\s*pub\s+(\w+)\s*:", line)
        if m:
            fields.add(m.group(1))
    return fields


def extract_ts_fields() -> set[str]:
    """Extract top-level field names from TypeScript RustProcessingResult interface."""
    content = TS_FILE.read_text()
    # Find the interface block — use brace counting for nested objects
    start = content.find("interface RustProcessingResult")
    if start == -1:
        print(f"ERROR: Could not find RustProcessingResult interface in {TS_FILE}")
        sys.exit(2)

    brace_start = content.index("{", start)
    depth = 0
    end = brace_start
    for i in range(brace_start, len(content)):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    block = content[brace_start + 1 : end]

    # Only extract top-level fields (depth 0)
    # A field like "grid_bounds: { ... } | null" starts at depth 0
    fields = set()
    depth = 0
    for line in block.split("\n"):
        if depth == 0:
            m = re.match(r"\s*(\w+)\??\s*:", line)
            if m:
                fields.add(m.group(1))
        # Track nested braces AFTER checking the field name
        depth += line.count("{") - line.count("}")
    return fields


def main():
    rust_fields = extract_rust_fields()
    ts_fields = extract_ts_fields()

    print(f"Rust ProcessingResult:       {sorted(rust_fields)}")
    print(f"TS   RustProcessingResult:    {sorted(ts_fields)}")

    # Compare
    only_rust = rust_fields - ts_fields
    only_ts = ts_fields - rust_fields

    if only_rust or only_ts:
        print("\nERROR: Tauri IPC contract drift detected!")
        if only_rust:
            print(f"  In Rust but not TypeScript: {sorted(only_rust)}")
        if only_ts:
            print(f"  In TypeScript but not Rust: {sorted(only_ts)}")
        print(f"\nRust:  {RUST_FILE.relative_to(ROOT)}")
        print(f"TS:    {TS_FILE.relative_to(ROOT)}")
        sys.exit(1)
    else:
        print("\nTauri IPC contract: in sync.")
        sys.exit(0)


if __name__ == "__main__":
    main()
