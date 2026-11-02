# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Trigger expression evaluator.

Workflow YAMLs declare triggers as ``metric: <id>`` + ``condition: "<op> <value>"``.
This module parses the condition and returns whether it fires for a given
metric value. Supports the six common comparisons plus simple range syntax
(``"> 5 < 10"``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Single comparison: <op><whitespace><number>. Op order matters — match the
# longer operators first so >= isn't misread as > with a leading "=".
_OP_PATTERN = re.compile(r"\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Comparison:
    op: str
    value: float

    def evaluate(self, x: float) -> bool:
        if self.op == ">":
            return x > self.value
        if self.op == ">=":
            return x >= self.value
        if self.op == "<":
            return x < self.value
        if self.op == "<=":
            return x <= self.value
        if self.op == "==":
            return x == self.value
        if self.op == "!=":
            return x != self.value
        raise ValueError(f"unknown operator {self.op!r}")


def parse_condition(condition: str) -> list[Comparison]:
    """Parse ``"> 5"`` or ``"> 5 < 10"`` into a list of Comparisons.

    All comparisons are AND'd together at evaluate time.
    Returns an empty list (= always-false) for unparseable input.
    """
    matches = _OP_PATTERN.findall(condition or "")
    return [Comparison(op=op, value=float(v)) for op, v in matches]


def metric_value(metrics: dict[str, Any], metric_id: str) -> float | None:
    """Coerce a value out of the pipe ``data`` dict.

    Accepts numeric and numeric-strings; returns None if the metric is missing
    or the value can't be coerced.
    """
    if metric_id not in metrics:
        return None
    raw = metrics[metric_id]
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def evaluate(condition: str, value: float) -> bool:
    """True if every comparison in ``condition`` holds for ``value``."""
    comparisons = parse_condition(condition)
    if not comparisons:
        return False
    return all(c.evaluate(value) for c in comparisons)
