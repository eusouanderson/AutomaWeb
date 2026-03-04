setup:
	poetry install
	poetry run playwright install chromium
	poetry run rfbrowser init

setup-dev:
	cp -n .env.example .env || true
	$(MAKE) setup

run:
	uvicorn app.main:app --reload

test:
	pytest -q

lint:
	python -m compileall app
