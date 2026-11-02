# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""CSV / JSON parsers — convert a file stream into list[dict[str, str]].

Type coercion happens later in the validator so each parser only needs to
produce raw string-or-passthrough values keyed by column name. CSV reads
the header row as the column names; JSON expects either an array of objects
or a single object (treated as one row).
"""

from __future__ import annotations

import csv
import json
from io import StringIO, TextIOWrapper
from typing import IO, Any


def parse_csv(stream: IO[bytes] | IO[str]) -> list[dict[str, str]]:
    """Read CSV bytes/text from ``stream`` and return one dict per data row.

    Strips whitespace from header and cell values. Rejects files where
    the header row is missing or has duplicate column names.
    """
    if isinstance(stream, (bytes, bytearray)):
        text = stream.decode("utf-8-sig")
    else:
        # File-like — peek at the first byte to decide bytes vs text.
        first = stream.read(0)
        if isinstance(first, bytes):
            raw = stream.read()
            assert isinstance(raw, (bytes, bytearray))
            text = raw.decode("utf-8-sig")
        else:
            chunk = stream.read()
            assert isinstance(chunk, str)
            text = chunk

    reader = csv.reader(StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("empty file") from exc

    header = [h.strip() for h in header]
    if len(set(header)) != len(header):
        dupes = sorted({h for h in header if header.count(h) > 1})
        raise ValueError(f"duplicate header columns: {dupes}")

    rows: list[dict[str, str]] = []
    for line in reader:
        if not any(cell.strip() for cell in line):
            continue  # skip blank lines
        if len(line) != len(header):
            raise ValueError(
                f"row has {len(line)} cells but header has {len(header)} columns: {line!r}"
            )
        rows.append({header[i]: line[i].strip() for i in range(len(header))})
    return rows


def parse_json(stream: IO[bytes] | IO[str] | bytes | str) -> list[dict[str, Any]]:
    """Read JSON. Accepts an array of objects or a single object."""
    if isinstance(stream, (bytes, bytearray)):
        text = stream.decode("utf-8-sig")
    elif isinstance(stream, str):
        text = stream
    elif isinstance(stream, TextIOWrapper):
        text = stream.read()
    else:
        raw = stream.read()
        text = raw.decode("utf-8-sig") if isinstance(raw, (bytes, bytearray)) else raw

    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("JSON array must contain only objects")
        return parsed
    raise ValueError("JSON must be an object or an array of objects")
