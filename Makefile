# rss-tool 开发入口。所有命令均可在仓库根目录执行。

PY      := backend/.venv/bin/python
PIP     := backend/.venv/bin/pip
UVICORN := backend/.venv/bin/uvicorn
PYTEST  := backend/.venv/bin/pytest
RUFF    := backend/.venv/bin/ruff
PNPM    := corepack pnpm

.PHONY: help setup setup-backend setup-frontend dev dev-backend dev-frontend test test-backend test-frontend lint lint-backend lint-frontend typecheck typecheck-frontend db-reset up down

help:
	@grep -E "^[a-z-]+:" Makefile | cut -d: -f1 | tr "\n" " "; echo

setup: setup-backend setup-frontend

setup-backend:
	uv venv backend/.venv
	uv pip install --python $(PY) -e "backend[dev]"

setup-frontend:
	cd frontend && $(PNPM) install

dev:
	@echo "后端 http://localhost:8000 ｜ 前端 http://localhost:5173"
	@trap "kill 0" INT TERM EXIT; \\
	 (cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) & \\
	 (cd frontend &&  dev) & \\
	 wait

dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && $(PNPM) dev

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/pytest -q

test-frontend:
	cd frontend && $(PNPM) vitest run

lint: lint-backend lint-frontend

lint-backend:
	cd backend && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests

lint-frontend:
	cd frontend && $(PNPM) lint

typecheck: typecheck-frontend

typecheck-frontend:
	cd frontend && $(PNPM) typecheck

db-reset:
	rm -rf backend/data
	@echo "已清空 backend/data，下次启动重建"

up:
	docker compose up --build

down:
	docker compose down
