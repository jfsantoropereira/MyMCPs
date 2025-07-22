# Brazilian Finance MCP Server Makefile

.PHONY: help install run test lint clean build deploy

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Install Python dependencies
	pip install -r requirements.txt

run:  ## Run the MCP server locally
	uvicorn server:app --host 0.0.0.0 --port 8000 --reload

test:  ## Run tests
	pytest tests/ -v

lint:  ## Run linting (flake8 and black)
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	black --check .

format:  ## Format code with black
	black .

clean:  ## Clean up temporary files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type f -name "*.db" -delete
	find . -type f -name "*.duckdb*" -delete

build:  ## Build Docker image
	docker build -t brazilian-finance-mcp .

deploy:  ## Deploy with docker-compose
	docker-compose up -d

stop:  ## Stop docker-compose services
	docker-compose down

logs:  ## Show docker-compose logs
	docker-compose logs -f

restart:  ## Restart services
	docker-compose restart

update-data:  ## Trigger data update
	curl -X POST http://localhost:8000/mcp/tools/call \
		-H "Content-Type: application/json" \
		-d '{"name": "refresh_data", "arguments": {"connector": "all"}}'

health:  ## Check service health
	curl http://localhost:8000/health