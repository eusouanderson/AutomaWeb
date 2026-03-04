FROM python:3.12-slim

# Instalar dependências do sistema para Robot Framework Browser
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    libgbm-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar Node.js (necessário para rfbrowser)
RUN wget -qO- https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Configurar diretório de trabalho
WORKDIR /app

# Copiar arquivos de dependências
COPY requirements.txt ./

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Instalar navegador para Playwright
RUN python -m playwright install --with-deps chromium

# Inicializar Robot Framework Browser (baixar navegadores)
RUN rfbrowser init --skip-browsers || echo "Browser init will be done on first run"

# Copiar código da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p app/static/reports app/static/projects

# Expor porta da aplicação
EXPOSE 8888

# Comando para rodar a aplicação
CMD ["python", "dev.py"]
