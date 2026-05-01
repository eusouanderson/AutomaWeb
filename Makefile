setup:
	poetry install
	$(MAKE) install-playwright
	poetry run rfbrowser init

setup-dev:
	cp -n .env.example .env || true
	$(MAKE) setup

install-playwright:
	@echo "📦 Installing Playwright browsers..."
	poetry run playwright install chromium
	@echo "✅ Playwright installation complete"

run:
	uvicorn app.main:app --reload

test:
	pytest

lint:
	python -m compileall app

.PHONY: setup setup-dev install-playwright run test lint
