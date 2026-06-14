.PHONY: help install dev test lint format clean docker-up docker-down benchmark

# Default target
help:
	@echo "AgentReliabilityLab — Development Commands"
	@echo ""
	@echo "  make install        Install Python dependencies"
	@echo "  make dev            Start API in development mode"
	@echo "  make test           Run all tests with coverage"
	@echo "  make lint           Run ruff linter"
	@echo "  make format         Format code with ruff"
	@echo "  make clean          Remove build artifacts and databases"
	@echo "  make docker-up      Start full stack with Docker Compose"
	@echo "  make docker-down    Stop Docker Compose stack"
	@echo "  make benchmark      Run all benchmarks"
	@echo "  make bench-sql      Run SQL agent benchmark"
	@echo "  make bench-rag      Run RAG agent benchmark"
	@echo "  make bench-security Run GitHub Security agent benchmark"
	@echo "  make seed-db        Seed the benchmark databases"

install:
	pip install -e . -r requirements.txt
	cp -n .env.example .env || true

dev:
	@cp -n .env.example .env || true
	mkdir -p data
	cd apps/api && uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	mkdir -p data
	PYTHONPATH=. pytest tests/ -v --cov=packages --cov-report=term-missing --cov-report=html:htmlcov

lint:
	ruff check packages/ apps/api/ tests/ benchmarks/

format:
	ruff format packages/ apps/api/ tests/ benchmarks/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf data/ htmlcov/ .pytest_cache/ dist/ *.egg-info

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v

benchmark: bench-sql bench-rag bench-security

bench-sql:
	@echo "Running SQL Agent Benchmark..."
	PYTHONPATH=. python benchmarks/sql_agent/run_benchmark.py

bench-rag:
	@echo "Running RAG Agent Benchmark..."
	PYTHONPATH=. python benchmarks/enterprise_rag/run_benchmark.py

bench-security:
	@echo "Running GitHub Security Agent Benchmark..."
	PYTHONPATH=. python benchmarks/github_security/run_benchmark.py

seed-db:
	@echo "Seeding benchmark databases..."
	PYTHONPATH=. python scripts/seed_databases.py
