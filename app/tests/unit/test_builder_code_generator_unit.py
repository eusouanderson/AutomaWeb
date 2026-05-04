from app.builder.code_generator import PlaywrightCodeGenerator


def test_normalize_selector_all_prefixes_and_fallbacks() -> None:
    g = PlaywrightCodeGenerator()

    assert g._normalize_selector("id:email") == "css=#email"
    assert g._normalize_selector("css:.btn") == "css=.btn"
    assert g._normalize_selector("xpath://div") == "xpath=//div"
    assert g._normalize_selector("css=#x") == "css=#x"
    assert g._normalize_selector("xpath=//a") == "xpath=//a"
    assert g._normalize_selector("#id") == "css=#id"
    assert g._normalize_selector("[name='q']") == "css=[name='q']"
    assert g._normalize_selector(".class") == "css=.class"
    assert g._normalize_selector("/html/body") == "xpath=/html/body"
    assert g._normalize_selector("(//div)[1]") == "xpath=(//div)[1]"
    assert g._normalize_selector("button") == "button"
    assert g._normalize_selector("aw") == "css=aw"
    assert g._normalize_selector("button.primary") == "button.primary"
    assert g._normalize_selector("text=raw") == "text=raw"


def test_make_selector_unique_branches() -> None:
    g = PlaywrightCodeGenerator()
    assert g._make_selector_unique("css=#x") == "css=#x >> nth=0"
    assert g._make_selector_unique("css=#x >> nth=0") == "css=#x >> nth=0"
    assert g._make_selector_unique("xpath=//a") == "xpath=//a"


def test_generate_without_steps_uses_about_blank_and_no_operation() -> None:
    g = PlaywrightCodeGenerator()
    out = g.generate([], start_url=None, prompt="")

    assert "New Page    about:blank" in out
    assert "# Nenhuma acao visual capturada." in out
    assert "No Operation" in out
    assert out.endswith("\n")


def test_generate_with_prompt_and_mixed_steps() -> None:
    g = PlaywrightCodeGenerator()
    out = g.generate(
        [
            {"action": "click", "selector": "#login", "description": "clicar login"},
            {"action": "input", "selector": "id:email", "value": "a@b.c"},
            {"action": "hover", "selector": "#x", "description": "unsupported"},
            {"action": "click", "description": "sem seletor"},
            {"type": "click", "selector": "button"},
        ],
        start_url="https://example.com",
        prompt="Fluxo de login",
    )

    assert "# Objetivo: Fluxo de login" in out
    assert "New Page    https://example.com" in out
    assert "# clicar login" in out
    assert "Click    css=#login >> nth=0" in out
    assert "Fill Text    css=#email >> nth=0    a@b.c" in out
    assert "# Step nao suportado" in out
    assert "# Step ignorado (sem seletor)" in out
    assert "Click    button" in out
    assert "Close Browser" in out
