.PHONY: up down ci format lint test

# Docker commands
up:
	docker-compose up --build -d

down:
	docker-compose down

# CI commands
ci: format lint test

format:
	docker-compose run --rm lambda_job black . --check
	docker-compose run --rm lambda_job isort . --check-only

lint:
	docker-compose run --rm lambda_job flake8 .
	docker-compose run --rm lambda_job mypy .

test:
	@echo "Running basic syntax check..."
	docker-compose run --rm lambda_job python -m py_compile api_data.py

# Terraform commands
tf-init:
	docker-compose run --rm terraform init

tf-plan:
	docker-compose run --rm terraform plan

tf-apply:
	docker-compose run --rm terraform apply -auto-approve

tf-destroy:
	docker-compose run --rm terraform destroy -auto-approve

# Local development
build-local:
	cd extract_api_data && docker build -t lambda-local .

run-local:
	docker run --rm -e Authorization="Bearer your-token" lambda-local

# Help
help:
	@echo "Available commands:"
	@echo "  up          - Start Docker containers"
	@echo "  down        - Stop Docker containers"
	@echo "  ci          - Run CI pipeline (format, lint, test)"
	@echo "  format      - Format code with black and isort"
	@echo "  lint        - Lint code with flake8 and mypy"
	@echo "  test        - Run basic tests"
	@echo "  tf-init     - Initialize Terraform"
	@echo "  tf-plan     - Plan Terraform changes"
	@echo "  tf-apply    - Apply Terraform changes"
	@echo "  tf-destroy  - Destroy Terraform resources"
	@echo "  build-local - Build Docker image locally"
	@echo "  run-local   - Run container locally"