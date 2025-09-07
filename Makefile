.PHONY: dev prod build clean logs test test-local setup install

# Development (with auto-reload)
dev:
	docker-compose up --build

# Development (detached)
dev-d:
	docker-compose up -d --build

# Production (without auto-reload)
prod:
	docker build -t vocab-api .
	docker run -p 8001:8001 vocab-api

# Build only
build:
	docker-compose build

# Stop containers
stop:
	docker-compose down

# View logs
logs:
	docker-compose logs -f

# Clean up
clean:
	docker-compose down -v
	docker system prune -f

# Restart
restart:
	docker-compose restart

# Setup virtual environment
setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

# Install dependencies
install:
	.venv/bin/pip install -r requirements.txt

# Run tests
test:
	python run_tests.py

# Run tests locally (without Docker)
test-local:
	source .venv/bin/activate && python run_tests.py

# Run specific test
test-flashcard:
	source .venv/bin/activate && python tests/test_flashcard_system.py

# Run comprehensive test
test-comprehensive:
	source .venv/bin/activate && python tests/comprehensive_test_suite.py

# Run API server locally
run-local:
	source .venv/bin/activate && python vocab_api.py

# Check code quality
lint:
	source .venv/bin/activate && python -m flake8 *.py tests/*.py --max-line-length=100 --ignore=E501,W503
