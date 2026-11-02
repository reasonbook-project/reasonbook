# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Validate parsed rows against an UploadSchema.

Coerces string values from CSV into the column's declared type, checks
constraints (min/max/max_length/pattern/enum), and reports per-row,
per-column errors. The result preserves the original row order so the
writer can map row-index to source line for error reports.

Pure logic — no DB, no IO. Tests import this directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from reasonbook.semantic.schema import UploadColumn, UploadSchema


class UploadValidationError(Exception):
    """Raised when a row fails validation hard enough to abort."""


@dataclass
class RowError:
    row_index: int  # 0-based, matches the input list
    column: str | None  # None for whole-row errors (e.g. duplicate period)
    message: str


@dataclass
class UploadValidationResult:
    rows: list[dict[str, Any]] = field(default_factory=list)  # coerced values
    errors: list[RowError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "row_count": len(self.rows),
            "errors": [
                {"row": e.row_index, "column": e.column, "message": e.message} for e in self.errors
            ],
        }


def _coerce(value: Any, column: UploadColumn) -> Any:
    """Coerce a raw cell value to the column's declared type.

    Empty string is treated as NULL — required-ness is checked separately
    so the caller knows the difference between "missing" and "wrong type".
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    s = str(value).strip()
    t = column.type
    if t == "string":
        return s
    if t == "integer":
        return int(s)
    if t == "float":
        return float(s)
    if t == "boolean":
        if s.lower() in {"true", "1", "yes", "y", "t"}:
            return True
        if s.lower() in {"false", "0", "no", "n", "f"}:
            return False
        raise ValueError(f"not a boolean: {s!r}")
    if t == "date":
        return date.fromisoformat(s)
    raise AssertionError(f"unhandled column type: {t}")


def _check_constraints(value: Any, column: UploadColumn) -> str | None:
    """Return an error message if ``value`` violates a constraint, else None."""
    if value is None:
        return None  # NULL passes — required-ness handled upstream
    if column.type in {"integer", "float"}:
        if column.min is not None and value < column.min:
            return f"{value} < min {column.min}"
        if column.max is not None and value > column.max:
            return f"{value} > max {column.max}"
    if column.type == "string":
        if column.max_length is not None and len(value) > column.max_length:
            return f"length {len(value)} > max_length {column.max_length}"
        if column.pattern is not None and not re.fullmatch(column.pattern, value):
            return f"value does not match pattern {column.pattern!r}"
    if column.enum is not None and value not in column.enum:
        return f"value {value!r} not in allowed enum {column.enum}"
    return None


def validate_rows(
    rows: list[dict[str, Any]],
    schema: UploadSchema,
) -> UploadValidationResult:
    """Validate every row against the schema. Reports all errors (no fail-fast).

    Per-row checks: every required column present and non-null, type
    coercion succeeds, constraints satisfied, no unknown columns. Cross-row
    check: the period column is unique across the upload.
    """
    result = UploadValidationResult()
    by_name = {c.name: c for c in schema.columns}
    valid_names = set(by_name)
    period_col = next(c for c in schema.columns if c.primary_key)

    seen_periods: set[Any] = set()
    for idx, raw in enumerate(rows):
        # Unknown columns — strict reject so the user knows their CSV header
        # has a typo before the data lands.
        unknown = set(raw) - valid_names
        for unknown_name in unknown:
            result.errors.append(
                RowError(row_index=idx, column=unknown_name, message="unknown column")
            )

        coerced: dict[str, Any] = {}
        for col in schema.columns:
            raw_val = raw.get(col.name)
            try:
                coerced_val = _coerce(raw_val, col)
            except (ValueError, TypeError) as exc:
                result.errors.append(
                    RowError(
                        row_index=idx,
                        column=col.name,
                        message=f"could not coerce to {col.type}: {exc}",
                    )
                )
                continue

            if coerced_val is None and col.required:
                result.errors.append(
                    RowError(
                        row_index=idx,
                        column=col.name,
                        message="required column is missing or empty",
                    )
                )
                continue

            err = _check_constraints(coerced_val, col)
            if err:
                result.errors.append(RowError(row_index=idx, column=col.name, message=err))
                continue

            coerced[col.name] = coerced_val

        # Period uniqueness check — only meaningful if the period coerced.
        period_val = coerced.get(period_col.name)
        if period_val is not None:
            if period_val in seen_periods:
                result.errors.append(
                    RowError(
                        row_index=idx,
                        column=period_col.name,
                        message=f"duplicate period {period_val!r} earlier in file",
                    )
                )
            else:
                seen_periods.add(period_val)

        if all(e.row_index != idx for e in result.errors):
            result.rows.append(coerced)

    return result
