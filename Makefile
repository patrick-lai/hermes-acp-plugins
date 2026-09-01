.PHONY: format verify

PLUGIN ?= plugins/hermes-acp

format:
	cd $(PLUGIN) && uv run --extra test ruff format .
	cd $(PLUGIN) && uv run --extra test ruff check --fix .

verify:
	cd $(PLUGIN) && uv run --extra test ruff format --check .
	cd $(PLUGIN) && uv run --extra test ruff check .
	cd $(PLUGIN) && uv run --extra test mypy hermes_acp
	cd $(PLUGIN) && uv run --extra test python -m build --no-isolation
	cd $(PLUGIN) && uv run --extra test pytest -q
