# AutomaWeb 🧪

Sistema de geração e execução automática de testes Robot Framework usando IA.

[![Docker Build](https://github.com/eusouanderson/AutomaWeb/actions/workflows/docker-build.yml/badge.svg)](https://github.com/eusouanderson/AutomaWeb/actions/workflows/docker-build.yml)
[![Tests](https://github.com/eusouanderson/AutomaWeb/actions/workflows/tests.yml/badge.svg)](https://github.com/eusouanderson/AutomaWeb/actions/workflows/tests.yml)

## Características

- 🤖 Geração de testes Robot Framework com IA (Groq/LLama)
- 🧪 Execução automática de testes com Robot Framework + Browser Library
- 📊 Relatórios MkDocs integrados
- 🎯 Interface web intuitiva
- 🐳 Containerizado com Docker

## Tecnologias

- **Backend**: FastAPI + SQLAlchemy (async)
- **Frontend**: Vanilla JS + Axios
- **Testes**: Robot Framework + Browser Library
- **IA**: Groq API (LLama 3.3 70B)
- **Documentação**: MkDocs Material

## Instalação

### Docker Hub / GitHub Container Registry

```bash
# 1. Puxar a imagem do GitHub Container Registry
docker pull ghcr.io/OWNER/automaweb:latest

# 2. Executar o container
docker run -d \
  -p 8888:8888 \
  -e GROQ_API_KEY=sua_chave_aqui \
  -v $(pwd)/app.db:/app/app.db \
  -v $(pwd)/reports:/app/app/static/reports \
  ghcr.io/OWNER/automaweb:latest

# 3. Acesse a aplicação
http://localhost:8888
```

### Docker Compose (Desenvolvimento)

```bash
# 1. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env e adicione sua GROQ_API_KEY

# 2. Execute com Docker Compose
docker-compose up -d

# 3. Acesse a aplicação
http://localhost:8888
```

### Local (com Poetry)

```bash
# 1. Instale as dependências
poetry install

# 1.1 (obrigatório para o Smart Element Scanner)
poetry run playwright install chromium

# 2. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env e adicione sua GROQ_API_KEY

# 3. Inicialize o Robot Framework Browser
poetry run rfbrowser init

# 4. Execute o servidor
poetry run python dev.py

# 5. Acesse a aplicação
http://localhost:8888
```

Atalho via Makefile:

```bash
make setup
```

Para garantir que rode em outro PC, versione também o arquivo de lock:

```bash
git add pyproject.toml poetry.lock requirements.txt Dockerfile Makefile
```

## Uso

1. **Criar Projeto**: Defina um nome, descrição e diretório de testes
2. **Gerar Testes**: Descreva o que deseja testar e a IA gera o código Robot Framework
3. **Executar Testes**: Execute os testes gerados e visualize relatórios em tempo real

## Estrutura do Projeto

```
AutomaWeb/
├── app/
│   ├── api/          # Rotas da API
│   ├── core/         # Configurações
│   ├── db/           # Database setup
│   ├── llm/          # Cliente Groq
│   ├── models/       # Modelos SQLAlchemy
│   ├── repositories/ # Camada de dados
│   ├── schemas/      # Schemas Pydantic
│   ├── services/     # Lógica de negócio
│   ├── static/       # Arquivos estáticos
│   └── tests/        # Testes unitários/integração
├── frontend/
│   └── public/       # Frontend HTML/CSS/JS
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Desenvolvimento

### Executar testes

```bash
# Com coverage
poetry run pytest --cov=app --cov-report=html

# Testes específicos
poetry run pytest app/tests/unit
poetry run pytest app/tests/integration
```

### Logs do Docker

```bash
docker-compose logs -f
```

### Reconstruir container

```bash
docker-compose up -d --build
```

## Variáveis de Ambiente

```env
GROQ_API_KEY=sua_chave_groq
DATABASE_URL=sqlite+aiosqlite:///./app.db
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TIMEOUT_SECONDS=30
GROQ_MAX_RETRIES=3
GROQ_CA_BUNDLE=
GROQ_INSECURE_SKIP_VERIFY=false
CACHE_TTL_SECONDS=300
STATIC_DIR=app/static
```

Se houver proxy corporativo com certificado próprio, configure `GROQ_CA_BUNDLE` com o caminho do arquivo `.crt` dentro do container.
Use `GROQ_INSECURE_SKIP_VERIFY=true` apenas para diagnóstico temporário.

Exemplo com Docker Compose:

```bash
# 1) Copie o certificado da empresa para ./certs
cp /caminho/empresa-ca.crt ./certs/empresa-ca.crt

# 2) No .env
GROQ_CA_BUNDLE=/app/certs/empresa-ca.crt
GROQ_INSECURE_SKIP_VERIFY=false

# 3) Reinicie
docker compose up -d --build
```

## API Endpoints

- `GET /` - Interface web
- `POST /projects` - Criar projeto
- `GET /projects` - Listar projetos
- `DELETE /projects/{id}` - Deletar projeto
- `POST /tests/generate` - Gerar teste com IA
- `POST /executions/run` - Executar testes
- `GET /docs` - Documentação Swagger

## Licença

MIT

## Banco de Dados

Por padrão usa SQLite. Para PostgreSQL, ajuste `DATABASE_URL` no `.env`:

```
DATABASE_URL=postgresql+asyncpg://automaweb:automaweb@localhost:5432/automaweb
```

## Docker (opcional)

```bash
docker-compose up -d
```
