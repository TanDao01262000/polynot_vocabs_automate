.PHONY: dev prod build clean logs

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
