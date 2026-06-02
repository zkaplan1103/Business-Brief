.PHONY: install smoke test lint

install:
	uv sync
	cd web && npm install

smoke:
	uv run python -m pytest tests/smoke.py -v

test:
	uv run python -m pytest tests/ -v

lint:
	uv run python -m py_compile pipeline/config.py reliability/call_model.py reliability/logger.py
	@echo "Lint OK"
