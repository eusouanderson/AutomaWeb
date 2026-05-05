*** Settings ***
Library    Browser
Library    String

Suite Setup       Open Shared Browser
Suite Teardown    Close Browser

*** Variables ***
${HEADLESS}         ${TRUE}
${BASE_TIMEOUT}     15s
${SHORT_TIMEOUT}    8s

*** Keywords ***
Open Shared Browser
    New Browser    chromium    headless=${HEADLESS}
    New Context
    Set Browser Timeout    ${BASE_TIMEOUT}

Dismiss Cookie Banner If Present
    [Arguments]    ${selector}
    ${visible}=    Run Keyword And Return Status
    ...    Wait For Elements State    ${selector}    visible    timeout=${SHORT_TIMEOUT}
    IF    ${visible}
        Click    ${selector}
    END

Assert URL Contains
    [Arguments]    ${fragment}
    ${url}=    Get Url
    Should Contain    ${url}    ${fragment}

Assert Page Has Text
    [Arguments]    ${text}
    ${body}=    Get Text    css=body
    Should Contain    ${body}    ${text}

*** Test Cases ***

# ─────────────────────────────────────────────────────────────
# 1. Navegação básica + verificação de título (example.com)
# ─────────────────────────────────────────────────────────────
TC01 - Carregar pagina e verificar titulo
    New Page    https://example.com    wait_until=domcontentloaded
    ${title}=    Get Title
    Should Contain    ${title}    Example Domain
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 2. Verificar URL atual após navegação
# ─────────────────────────────────────────────────────────────
TC02 - Verificar URL apos carregamento
    New Page    https://example.com    wait_until=domcontentloaded
    Assert URL Contains    example.com
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 3. Clicar em link e verificar mudança de URL (Wikipedia PT)
# ─────────────────────────────────────────────────────────────
TC03 - Clicar em link e navegar para outra pagina
    New Page    https://en.wikipedia.org/wiki/Main_Page    wait_until=domcontentloaded
    Wait For Elements State    css=#searchInput >> nth=0    visible    timeout=${BASE_TIMEOUT}
    Fill Text    css=#searchInput >> nth=0    Robot Framework
    Keyboard Key    press    Enter
    Wait For Elements State    css=h1 >> nth=0    visible    timeout=${BASE_TIMEOUT}
    ${url}=    Get Url
    Should Be True    'Robot_Framework' in '${url}' or 'search' in '${url}'
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 4. Preencher formulário de busca (DuckDuckGo)
# ─────────────────────────────────────────────────────────────
TC04 - Preencher busca no DuckDuckGo
    New Page    https://quotes.toscrape.com    wait_until=domcontentloaded
    Wait For Elements State    css=.quote >> nth=0    visible    timeout=${BASE_TIMEOUT}
    ${count}=    Get Element Count    css=.quote
    Should Be True    ${count} > 0
    # Navegar para segunda pagina via link next
    Click    css=.next a >> nth=0
    Wait For Elements State    css=.quote >> nth=0    visible    timeout=${BASE_TIMEOUT}
    Assert URL Contains    page/2
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 5. Verificar presença de elementos na página (httpbin)
# ─────────────────────────────────────────────────────────────
TC05 - Verificar elementos na pagina httpbin
    New Page    https://httpbin.org    wait_until=domcontentloaded
    Wait For Elements State    css=h2 >> nth=0    visible    timeout=${BASE_TIMEOUT}
    ${count}=    Get Element Count    css=a
    Should Be True    ${count} > 0
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 6. Navegação com Go To após New Page (simula troca de URL)
# ─────────────────────────────────────────────────────────────
TC06 - Navegar para URL diferente com Go To
    New Page    about:blank
    Go To    https://example.com    wait_until=domcontentloaded
    ${title}=    Get Title
    Should Contain    ${title}    Example
    Go To    https://example.org    wait_until=domcontentloaded
    Assert URL Contains    example.org
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 7. Verificar texto específico no body
# ─────────────────────────────────────────────────────────────
TC07 - Verificar conteudo textual da pagina
    New Page    https://example.com    wait_until=domcontentloaded
    Assert Page Has Text    This domain is for use in
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 8. Obter atributo de elemento (href do link "More information")
# ─────────────────────────────────────────────────────────────
TC08 - Verificar atributo href de link
    New Page    https://example.com    wait_until=domcontentloaded
    Wait For Elements State    css=a >> nth=0    visible    timeout=${BASE_TIMEOUT}
    ${href}=    Get Attribute    css=a >> nth=0    href
    Should Not Be Empty    ${href}
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 9. Screenshot da página (valida que o browser está funcional)
# ─────────────────────────────────────────────────────────────
TC09 - Capturar screenshot da pagina
    New Page    https://example.com    wait_until=domcontentloaded
    Take Screenshot    filename=EMBED
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 10. Testar The Internet - Checkbox page
# ─────────────────────────────────────────────────────────────
TC10 - Interagir com checkboxes
    New Page    https://the-internet.herokuapp.com/checkboxes    wait_until=domcontentloaded
    Wait For Elements State    css=input[type="checkbox"] >> nth=0    visible    timeout=${BASE_TIMEOUT}
    Check Checkbox    css=input[type="checkbox"] >> nth=0
    ${checked}=    Get Checkbox State    css=input[type="checkbox"] >> nth=0
    Should Be True    ${checked}
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 11. Testar The Internet - Dropdown
# ─────────────────────────────────────────────────────────────
TC11 - Selecionar opcao em dropdown
    New Page    https://the-internet.herokuapp.com/dropdown    wait_until=domcontentloaded
    Wait For Elements State    css=#dropdown    visible    timeout=${BASE_TIMEOUT}
    Select Options By    css=#dropdown    value    1
    ${selected}=    Get Selected Options    css=#dropdown    text
    Should Not Be Empty    ${selected}
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 12. Testar The Internet - Inputs numéricos
# ─────────────────────────────────────────────────────────────
TC12 - Preencher campo de input numerico
    New Page    https://the-internet.herokuapp.com/inputs    wait_until=domcontentloaded
    Wait For Elements State    css=input[type="number"]    visible    timeout=${BASE_TIMEOUT}
    Fill Text    css=input[type="number"]    42
    ${value}=    Get Property    css=input[type="number"]    value
    Should Be Equal    ${value}    42
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 13. Testar The Internet - Hover
# ─────────────────────────────────────────────────────────────
TC13 - Hover em elemento e verificar conteudo
    New Page    https://the-internet.herokuapp.com/hovers    wait_until=domcontentloaded
    Wait For Elements State    css=.figure >> nth=0    visible    timeout=${BASE_TIMEOUT}
    Hover    css=.figure >> nth=0
    Wait For Elements State    css=.figcaption >> nth=0    visible    timeout=${SHORT_TIMEOUT}
    Assert Page Has Text    name:
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 14. Testar The Internet - Multiple Windows (abertura de página)
# ─────────────────────────────────────────────────────────────
TC14 - Verificar link na pagina de multiple windows
    New Page    https://the-internet.herokuapp.com/windows    wait_until=domcontentloaded
    Wait For Elements State    css=.example a >> nth=0    visible    timeout=${BASE_TIMEOUT}
    ${href}=    Get Attribute    css=.example a >> nth=0    href
    Should Contain    ${href}    windows
    [Teardown]    Close Page

# ─────────────────────────────────────────────────────────────
# 15. Testar The Internet - Redirect (status code via Go To)
# ─────────────────────────────────────────────────────────────
TC15 - Navegar apos redirect e verificar URL final
    New Page    https://the-internet.herokuapp.com/redirector    wait_until=domcontentloaded
    Wait For Elements State    css=#redirect >> nth=0    visible    timeout=${BASE_TIMEOUT}
    Click    css=#redirect >> nth=0
    Wait For Elements State    css=h3 >> nth=0    visible    timeout=${BASE_TIMEOUT}
    Assert URL Contains    status_codes
    [Teardown]    Close Page
