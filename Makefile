.PHONY: run-ux run-agent ralph install lint test

# Start the web dashboard (backend API + frontend dev server)
run-ux:
	python start.py

# Run the CLI agent against a challenge URL
URL ?= https://detective.kusto.io/inbox/onboarding
run-agent:
	python -m detective.main --follow $(URL)

# Run the Ralph loop (multi-iteration agent)
ITERS ?= 5
ralph:
	python ralph.py $(ITERS)

# Install dependencies
install:
	python -m pip install -e ".[dev]"
	python -m playwright install chromium
	cd web && npm install

# Lint
lint:
	python -m ruff check src/

# Test
test:
	python -m pytest tests/ -v
