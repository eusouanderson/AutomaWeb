*** Settings ***
Library    Browser

*** Variables ***
${HEADLESS}    ${FALSE}

*** Test Cases ***
Navegar pelo Menu Principal e Acessar Fale Conosco
    New Browser    chromium    headless=${HEADLESS}
    New Context
    Set Browser Timeout    30s
    New Page    about:blank
    Go To    https://www.comerc.com.br/    wait_until=domcontentloaded    timeout=0
    Wait For Elements State    css=#hs-eu-confirmation-button >> nth=0    visible    timeout=10s
    Evaluate JavaScript    css=#hs-eu-confirmation-button >> nth=0    (element) => element.click()
    Wait For Elements State    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(1) > a >> nth=0    visible
    Click    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(1) > a >> nth=0
    Wait For Elements State    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(2) > a >> nth=0    visible
    Click    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(2) > a >> nth=0
    Wait For Elements State    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(3) > a >> nth=0    visible
    Click    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(3) > a >> nth=0
    Wait For Elements State    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(4) > a >> nth=0    visible
    Click    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(4) > a >> nth=0
    Wait For Elements State    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(5) > a >> nth=0    visible
    Click    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(5) > a >> nth=0
    Wait For Elements State    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(7) > a >> nth=0    visible
    Click    css=header > div > div > div > div > div > div > div > div:nth-of-type(2) > div > div > div > div > div > span > div > ul > li:nth-of-type(7) > a >> nth=0
    # Banner de cookies pode não aparecer novamente na segunda página — clique seguro via page.evaluate
    Run Keyword And Ignore Error    Evaluate JavaScript    ${None}    () => { const btn = document.querySelector('#hs-eu-confirmation-button'); if (btn) btn.click(); }
    Wait For Elements State    css=#firstname-bf2ed18f-a579-4785-adf8-9ca49dd6bca6_2154 >> nth=0    visible
    Click    css=#firstname-bf2ed18f-a579-4785-adf8-9ca49dd6bca6_2154 >> nth=0
    Fill Text    css=#firstname-bf2ed18f-a579-4785-adf8-9ca49dd6bca6_2154 >> nth=0    anderson.silva@comerc.com.br
    [Teardown]    Close Browser