# AutomaWeb Frontend

Interface web para o sistema de geração de testes Robot Framework.

## Instalação

```bash
cd frontend
npm install
```

## Desenvolvimento

O frontend é servido automaticamente pelo FastAPI. Basta rodar o backend:

```bash
cd ..
poetry run python dev.py
```

Acesse: http://localhost:8888

## Bibliotecas Utilizadas

- **Axios**: Cliente HTTP para chamadas à API
- **Toastify.js**: Notificações toast elegantes

## Estrutura

```
frontend/
├── package.json       # Dependências npm
└── public/
    ├── index.html    # HTML principal
    ├── styles.css    # Estilos
    └── app.js        # Lógica da aplicação
```

## Funcionalidades

- ✅ Criar e listar projetos
- ✅ Gerar testes com IA (Groq)
- ✅ Visualizar código gerado
- ✅ Copiar código
- ✅ Download arquivo .robot
