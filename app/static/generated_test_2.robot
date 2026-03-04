```robot
*** Settings ***
Library    PlaywrightLibrary

*** Test Cases ***
Testar Botão
    Criar Navegador   -headed
    Novo Contexto
    Nova Guia    http://localhost:8000
    Clicar    id:botao
    Fechar Navegador
```

**Observação:** substitua `id:botao` pelo seletor correto do botão que você deseja testar. Para fazer isso, você precisa saber o id, name, classe, etc. do elemento HTML do botão. Caso não saiba o seletor, você pode inspecionar o elemento no navegador para encontrar o seletor correto.