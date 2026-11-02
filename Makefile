# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
.PHONY: help install migrate test test-pg lint format web-install web-build web-test docker-build up down seed

help:
	@echo "Reasonbook make targets:"
	@echo "  install     - pip install -e .[dev]"
	@echo "  migrate     - alembic upgrade head"
	@echo "  test        - pytest (SQLite)"
	@echo "  test-pg     - pytest against REASONBOOK_DATABASE_URL (PostgreSQL)"
	@echo "  lint        - ruff check ."
	@echo "  format      - ruff format ."
	@echo "  web-install - cd web && pnpm install"
	@echo "  web-build   - cd web && pnpm build"
	@echo "  web-test    - cd web && pnpm test"
	@echo "  docker-build- docker build -t reasonbook:1.0.0 ."
	@echo "  up / down   - docker compose up --build / down"

install:
	pip install -e ".[dev]"

migrate:
	alembic upgrade head

test:
	pytest

test-pg:
	@test -n "$(REASONBOOK_DATABASE_URL)" || (echo "set REASONBOOK_DATABASE_URL to a postgresql:// url" && exit 1)
	pytest

lint:
	ruff check .

format:
	ruff format .

web-install:
	cd web && pnpm install

web-build:
	cd web && pnpm build

web-test:
	cd web && pnpm test

docker-build:
	docker build -t reasonbook:1.0.0 .

up:
	docker compose up --build

down:
	docker compose down
