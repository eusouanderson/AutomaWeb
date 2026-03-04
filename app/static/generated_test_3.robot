```robot
*** Settings ***
Library    Browser

*** Test Cases ***
Abrir Google
    New Browser    chromium
    New Page        https://google.com
    Close Browser
```