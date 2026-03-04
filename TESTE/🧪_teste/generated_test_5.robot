Library    Browser

${URL}    https://example.com

Verificar Título da Página
    New browser    chrome
    New page    ${URL}
    Verify title    Example Domain

Verificar Elementos da Página
    New browser    chrome
    New page    ${URL}
    Verify element    id:footer
    Verify element    id:content

Verificar Links da Página
    New browser    chrome
    New page    ${URL}
    Verify link    More information...
    Verify link    example.net

Verify title
    [Arguments]    ${title}
    Get title    ==    ${title}

Verify element
    [Arguments]    ${element}
    Get element    ${element}

Verify link
    [Arguments]    ${link}
    Get text    ${link}    ==    ${link}
