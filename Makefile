# Makefile

# Default target
.DEFAULT_GOAL := help

# Application name
APP_NAME := Checkr

# Docker image name
DOCKER_IMAGE := $(APP_NAME)

# Kubernetes directory
K8S_DIR := k8s/

# Colors for output
CYAN  := \033[36m
RESET := \033[0m

# to convert repo in single file and restore it
SCRIPT_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))
SNAPSHOT := $(SCRIPT_DIR).snapshot.txt
## ---------- General Commands ----------

.PHONY: help
help:  ## Show available commands
	@echo "$(CYAN)Available commands:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-15s$(RESET) %s\n", $$1, $$2}'


.PHONY: snapshot
snapshot:
	 find . -type f -not -path './dev/*' -not -path './uv.lock' -not -path './.git/*' -not -path '**/__pycache__/*' -not -path '**/.DS_Store' -not -path './.venv/*' -not -path './.*' -exec bash -c 'printf "\n>>> %s\n" "{}"; cat "{}"' \; > ./.snapshot.txt

.PHONY: restore
restore:
	@echo "Restoring files from $(SNAPSHOT) into $(SCRIPT_DIR)"
	@awk -v base_dir="$(SCRIPT_DIR)" '\
		function get_dir(path,  n, parts, dir) {\
			n = split(path, parts, "/");\
			dir = parts[1];\
			for (i = 2; i < n; i++) dir = dir "/" parts[i];\
			return (n > 1) ? dir : ".";\
		}\
		function remove_last_blank_line(file,   cmd, last) {\
			cmd = "tail -n 1 '\''" file "'\''";\
			cmd | getline last;\
			close(cmd);\
			if (last == "") {\
				cmd = "sed -i \"\" -e '\''$$d'\'' '\''" file "'\''";\
				system(cmd);\
			}\
		}\
		BEGIN { out = ""; first = 1 }\
		/^>>> / {\
			if (!first && out != "") {\
				close(out);\
				remove_last_blank_line(out);\
			}\
			first = 0;\
			relpath = substr($$0, 5);\
			gsub(/^[.]\//, "", relpath);\
			dir = get_dir(relpath);\
			system("mkdir -p '\''" base_dir "/" dir "'\''");\
			out = base_dir "/" relpath;\
			system("> '\''" out "'\''");\
			next;\
		}\
		{ if (out != "") print >> out }\
		END {\
			if (out != "") {\
				close(out);\
				remove_last_blank_line(out);\
			}\
		}\
	' "$(SNAPSHOT)"

## ---------- Local Development ----------
.PHONY: dev-init
dev-init:  ## Initialize development environment
	python3 -m uv venv
	python3 -m uv pip install --dev
	python3 -m uv run pre-commit install

.PHONY: build
build:  fetch-static-js ## Build and run application
	python3 -m pip install uv && \
	python3 -m uv sync --frozen --no-cache && \
	.venv/bin/fastapi run entrypoint.py

.PHONY: run
run:  ## Run application
	python3 -m uv run entrypoint.py

PHONY: fetch-static-js
fetch-static-js:
	@echo "📥 Downloading JS assets..."
	@mkdir -p static/pyodide
	@cd static/pyodide && \
	for file in python_stdlib.zip pyodide.asm.wasm pyodide.js pyodide-lock.json annotated_types-0.6.0-py3-none-any.whl typing_extensions-4.11.0-py3-none-any.whl pyodide.asm.js pydantic-2.10.5-py3-none-any.whl pydantic_core-2.27.2-cp312-cp312-pyodide_2024_0_wasm32.whl ; do \
		curl -LO https://cdn.jsdelivr.net/pyodide/v0.27.5/full/$$file; \
	done

## ---------- Code Quality ----------

.PHONY: lint
lint:  ## Run linting (Python example)
	python3 -m uv run ruff check --fix .

.PHONY: commit
commit:  ## Auto-format code (Python example)
	python3 -m uv run cz c

.PHONY: push
push: ## make commit using commitizen
	git add . && make commit && git push

## ---------- Testing ----------

.PHONY: test
test:  ## Run tests
	python3 -m uv run pytest -s

.PHONY: test-coverage
test-coverage:  ## Run tests with coverage report
	python3 -m uv run pytest --cov=.

## ---------- Deployment ----------

.PHONY: deploy
deploy:  ## Deploy application using Kubernetes
	kubectl apply -f $(K8S_DIR)

.PHONY: undeploy
undeploy:  ## Remove deployment from Kubernetes
	kubectl delete -f $(K8S_DIR)

.PHONY: logs
logs:  ## Show logs of the running application
	docker logs -f $(shell docker ps -q --filter ancestor=$(DOCKER_IMAGE))

## ---------- Docker commands ----------

.PHONY: docker-build
docker-build:  ## Build the Docker image
	docker build -t $(DOCKER_IMAGE) .

.PHONY: docker-run
docker-run:  ## Run the Docker container
	docker run -p 8080:8080 $(DOCKER_IMAGE)

.PHONY: docker-clean
docker-clean:  ## Remove Docker images and containers
	docker system prune -f

.PHONY: docker-stop
docker-stop:  ## Stop all running Docker containers
	docker ps -q | xargs -r docker stop

.PHONY: docker-shell
docker-shell:  ## Open an interactive shell inside the running container
	docker exec -it $(shell docker ps -q --filter ancestor=$(DOCKER_IMAGE)) /bin/sh

.PHONY: docker-restart
docker-restart:  ## Restart the application
	docker restart $(shell docker ps -q --filter ancestor=$(DOCKER_IMAGE))

.PHONY: docker-status
docker-status:  ## Show running containers
	docker ps
