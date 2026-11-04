.PHONY: test lint format docs docs-clean docs-check tidy ci

test:
	uv run pytest

lint:
	uv run ruff check . --fix

format:
	uv run black src tests

docs:
	rm -f docs/api/generated/*.rst
	uv run sphinx-build -M html docs docs/_build

docs-clean:
	rm -rf docs/api/generated
	rm -rf docs/_build
	uv run sphinx-build -M html docs docs/_build

docs-check:
	uv run sphinx-build -W --keep-going -b html docs docs/_build/html

tidy: lint format

ci:
	uv run pytest
	uv run ruff check .
	uv run mypy -p stanwell
	uv lock --locked
	uv run black --check src tests
