*** Settings ***
Library    Browser

*** Test Cases ***
Open Example
    New Browser    chromium
    New Page    https://example.com
    Get Title    ==    Example Domain
    Close Browser
