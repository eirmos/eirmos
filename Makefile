# eirmos build targets
#
# Common workflows:
#   make test           run unit tests
#   make coverage       run tests under coverage with the 90% gate
#   make build          build sdist + wheel into ./dist
#   make pyz            build a single-file zipapp (requires shiv)
#   make uv-install     install locally with `uv tool install`
#   make uvx            run one-shot with `uvx --from .`
#   make clean          remove build artefacts

PACKAGE := eirmos
SCRIPT  := eirmos
DIST    := dist
PYZ     := $(DIST)/$(SCRIPT).pyz

.PHONY: test coverage build pyz uv-install uvx clean help

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

test: ## Run unit tests
	python -m unittest discover -s tests

coverage: ## Run tests with coverage and the 90% gate
	python -m coverage run --source=$(PACKAGE) -m unittest discover -s tests
	python -m coverage report -m --fail-under=90

build: ## Build sdist + wheel into ./dist
	uv build

pyz: $(PYZ) ## Build a single-file zipapp (./dist/$(SCRIPT).pyz)

$(PYZ): pyproject.toml $(shell find $(PACKAGE) -name '*.py')
	@mkdir -p $(DIST)
	python -m shiv \
		--console-script $(SCRIPT) \
		--output-file $(PYZ) \
		--compressed \
		--reproducible \
		--python '/usr/bin/env python3' \
		.
	@echo
	@echo "Built $(PYZ) — run with: ./$(PYZ) <path>"
	@ls -lh $(PYZ)

uv-install: build ## Install locally with `uv tool install`
	uv tool install --reinstall --from ./dist/$(PACKAGE)-*.whl $(SCRIPT)

uvx: ## Run one-shot via `uvx --from .` (no install)
	uvx --from . $(SCRIPT) --help

clean: ## Remove build artefacts
	rm -rf build dist *.egg-info .coverage htmlcov
	find . -name '__pycache__' -type d -exec rm -rf {} +
