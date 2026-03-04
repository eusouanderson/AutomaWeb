# AutomaWeb

Backend em FastAPI para geração de testes web em Robot Framework usando Groq.

## Requisitos
- Python 3.12+
- (Opcional) Docker para PostgreSQL

## Configuração
1. Copie o arquivo de ambiente:
   - `cp .env.example .env`
2. Atualize a variável `GROQ_API_KEY` no arquivo `.env`.

## Instalação
```bash
pip install -r requirements.txt
```

## Executar

**Desenvolvimento (com reload):**
```bash
poetry run python dev.py
```

**Produção (com workers):**
```bash
poetry run python start.py
```

Ou diretamente:
```bash
poetry run uvicorn app.main:app --reload
```

## Endpoints
- `POST /projects`
- `GET /projects`
- `POST /tests/generate`
- `GET /tests/{id}`
- `GET /tests/{id}/download`

## Testes
```bash
pytest -q
```

## Robot Framework + Playwright
Exemplo em `app/tests/e2e/example.robot`.

## Banco de Dados
Por padrão usa SQLite. Para PostgreSQL, ajuste `DATABASE_URL` no `.env`:
```
DATABASE_URL=postgresql+asyncpg://automaweb:automaweb@localhost:5432/automaweb
```

## Docker (opcional)
```bash
docker-compose up -d
```
