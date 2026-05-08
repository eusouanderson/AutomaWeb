FROM python:3.12-slim

# Instalar dependências do sistema para Robot Framework Browser
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    libgbm-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar Node.js e npm
RUN apt-get update \
    && apt-get install -y nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Configurar diretório de trabalho
WORKDIR /app

# Copiar arquivos de dependências Python
COPY requirements.txt ./

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Nota: Playwright e Robot Framework Browser serão inicializados em runtime
# no primeiro acesso (ver app/main.py lifespan) para evitar problemas com
# certificados SSL corporativos durante o build

# Instalar dependências do frontend (usando npm ao invés de pnpm para compatibilidade)
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# Copiar código da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p app/static/reports app/static/projects

# Expor porta da aplicação
EXPOSE 8888

# Comando para rodar a aplicação
CMD ["python", "dev.py"]
