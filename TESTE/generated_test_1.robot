Library    Browser

Abrir Chrome e Acessar Google
    ${chrome} =    Launch Browser    chromium
    ${page} =      Create Context And Page    ${chrome}
    Go To    https://www.google.com
    Close Browser    ${chrome}
```
