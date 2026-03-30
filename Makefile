.PHONY: help setup dev up down logs clean build test

help:  ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## First-time setup
	cp -n .env.example .env || true
	cd frontend && npm install
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

dev: ## Start development (backend + frontend without Docker)
	@echo "Starting backend..."
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
	@echo "Starting frontend..."
	cd frontend && npm run dev &
	@echo "SCL-Governor running at http://localhost:5173"

up: ## Start all services with Docker Compose
	docker compose up -d --build
	@echo "SCL-Governor UI: http://localhost:3000"
	@echo "Backend API: http://localhost:8000/docs"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3001 (admin/sclgovernor)"

down: ## Stop all services
	docker compose down

logs: ## Tail all logs
	docker compose logs -f

logs-backend: ## Tail backend logs
	docker compose logs -f backend

build: ## Build all containers
	docker compose build

clean: ## Remove containers, volumes, and build artifacts
	docker compose down -v --remove-orphans
	rm -rf frontend/node_modules frontend/dist
	rm -rf backend/.venv backend/__pycache__

test-backend: ## Run backend tests
	cd backend && python -m pytest tests/ -v

typecheck: ## TypeScript type check
	cd frontend && npx tsc --noEmit
