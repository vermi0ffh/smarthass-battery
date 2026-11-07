PYTHON := .venv/bin/python
VENV := .venv/bin/python
# The code directories present (lint and typecheck work on a partial checkout)
SRC := $(wildcard custom_components tests review)
TYPED := $(wildcard custom_components review)

.PHONY: help install test test-model lint lint-fix format typecheck review

help:
	@echo "make install    — dev venv (Python 3.14, Home Assistant pinned by requirements_test.txt)"
	@echo "make test       — every test, coverage ≥ 95 % (before every commit)"
	@echo "make test-model — the model's tests only (fast, no Home Assistant)"
	@echo "make lint       — ruff check + format check (lint-fix / format to fix)"
	@echo "make typecheck  — mypy on the integration"
	@echo "make review     — AI review of the changed Python files (BASE=, AXES=, ENGINE=, MODEL=)"

$(VENV):
	uv venv --python 3.14 .venv
	uv pip install --python $(PYTHON) -r requirements_test.txt

install: $(VENV)
	uv pip install --python $(PYTHON) -r requirements_test.txt

test: $(VENV)
	$(PYTHON) -m pytest -q --cov=custom_components/smart_hass_battery --cov-report=term-missing:skip-covered --cov-fail-under=95

test-model: $(VENV)
	$(PYTHON) -m pytest -q tests/model

lint: $(VENV)
	$(PYTHON) -m ruff check $(SRC)
	$(PYTHON) -m ruff format --check $(SRC)

lint-fix: $(VENV)
	$(PYTHON) -m ruff check --fix $(SRC)
	$(PYTHON) -m ruff format $(SRC)

format: $(VENV)
	$(PYTHON) -m ruff format $(SRC)

typecheck: $(VENV)
	$(PYTHON) -m mypy $(TYPED) --exclude 'review/tests'

review: $(VENV)
	$(PYTHON) -m review $(if $(BASE),--base $(BASE)) $(if $(AXES),--axes $(AXES)) $(if $(ENGINE),--engine $(ENGINE)) $(if $(MODEL),--model $(MODEL)) $(if $(REVIEW_LANG),--language $(REVIEW_LANG)) $(if $(BASELINE),--baseline)
