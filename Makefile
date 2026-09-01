.PHONY: format verify

format:
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

verify:
	.venv/bin/ruff format --check .
	.venv/bin/ruff check .
	.venv/bin/mypy hermes_acp
	.venv/bin/python -m build --no-isolation
	.venv/bin/python -m pytest -q
