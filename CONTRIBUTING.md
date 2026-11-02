# Contributing to Reasonbook

Thank you for your interest in contributing to Reasonbook. This guide
explains how to get set up, how we handle contributions, and what we
expect from pull requests.

## Developer Certificate of Origin (DCO)

All commits must be signed off using the Developer Certificate of Origin
(DCO). Sign off by committing with:

```bash
git commit -s
```

This adds a `Signed-off-by:` line to your commit message, for example:

```
Signed-off-by: Christopher Johnson <you@example.com>
```

The DCO 1.1 is a lightweight statement certifying that you wrote the
contribution or otherwise have the right to submit it under the project's
open-source license. By signing off, you affirm that certification for the
contribution. Pull requests containing unsigned commits will not be merged.

## Development setup

Reasonbook requires Python >= 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

For the frontend:

```bash
cd web && pnpm install
```

## Running tests

Run the backend test suite against SQLite (the default):

```bash
pytest
```

To run against PostgreSQL, set the database URL first:

```bash
export REASONBOOK_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/db
pytest
```

Run the frontend unit tests:

```bash
cd web && pnpm test
```

Lint and format:

```bash
ruff check .
ruff format .
```

## Pull request expectations

- Keep pull requests small and focused.
- Include tests for new behavior.
- Run the test suite on SQLite before submitting.
- Keep the SPDX header on new source files:

```python
# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
```
