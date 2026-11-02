# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Manual CSV upload pipeline.

End-to-end shape:

  multipart CSV → parser.parse_csv → validator.validate_rows → writer.write_rows

The writer inserts validated rows directly into the workflow's local
``pipe_<workflow>`` staging table. From there the ingestion job reads the
latest period and evaluates triggers. There is no external producer — the
data path is entirely local.

The validator + parser are pure logic (no DB) and reusable from CLI tools
or future async pipelines.
"""

from reasonbook.uploads.parser import parse_csv, parse_json
from reasonbook.uploads.validator import (
    UploadValidationError,
    UploadValidationResult,
    validate_rows,
)
from reasonbook.uploads.writer import write_rows

__all__ = [
    "parse_csv",
    "parse_json",
    "validate_rows",
    "write_rows",
    "UploadValidationError",
    "UploadValidationResult",
]
