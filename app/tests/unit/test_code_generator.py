from app.builder.code_generator import PlaywrightCodeGenerator


def test_normalize_selector_handles_supported_prefixes() -> None:
    generator = PlaywrightCodeGenerator()

    assert generator._normalize_selector('id:login') == 'css=#login'
    assert generator._normalize_selector('css:.btn-primary') == 'css=.btn-primary'
    assert generator._normalize_selector('xpath://button') == 'xpath=//button'
    assert generator._normalize_selector('css=#ready') == 'css=#ready'
    assert generator._normalize_selector('xpath=//div') == 'xpath=//div'


def test_normalize_selector_handles_css_xpath_and_fallback_inputs() -> None:
    generator = PlaywrightCodeGenerator()

    assert generator._normalize_selector('#submit') == 'css=#submit'
    assert generator._normalize_selector("[data-testid='save']") == "css=[data-testid='save']"
    assert generator._normalize_selector('.card') == 'css=.card'
    assert generator._normalize_selector('//main') == 'xpath=//main'
    assert generator._normalize_selector('(//button)[1]') == 'xpath=(//button)[1]'
    assert generator._normalize_selector('bww') == 'css=bww'
    assert generator._normalize_selector('button.primary') == 'button.primary'
    assert generator._normalize_selector('text=Salvar') == 'text=Salvar'


def test_make_selector_unique_only_changes_css_without_nth() -> None:
    generator = PlaywrightCodeGenerator()

    assert generator._make_selector_unique('css=#submit') == 'css=#submit >> nth=0'
    assert generator._make_selector_unique('css=#submit >> nth=0') == 'css=#submit >> nth=0'
    assert generator._make_selector_unique('xpath=//button') == 'xpath=//button'


def test_generate_returns_no_operation_when_no_steps() -> None:
    generator = PlaywrightCodeGenerator()

    code = generator.generate([], start_url=None, prompt='   ')

    assert 'New Page    about:blank' in code
    assert 'No Operation' in code
    assert '# Nenhuma acao visual capturada.' in code


def test_generate_includes_prompt_and_ignores_step_without_selector() -> None:
    generator = PlaywrightCodeGenerator()

    code = generator.generate(
        [
            {'action': 'click', 'selector': '', 'description': 'step vazio'},
            {'type': 'hover', 'selector': '#menu', 'description': 'abrir menu'},
        ],
        start_url='https://example.com',
        prompt='Validar menu',
    )

    assert '# Objetivo: Validar menu' in code
    assert 'New Page    https://example.com' in code
    assert "# Step ignorado (sem seletor): {'action': 'click', 'selector': '', 'description': 'step vazio'}" in code
    assert '# abrir menu' in code
    assert "# Step nao suportado: {'type': 'hover', 'selector': '#menu', 'description': 'abrir menu'}" in code
    assert code.strip().endswith('Close Browser')


def test_generate_supports_click_and_input_steps() -> None:
    generator = PlaywrightCodeGenerator()

    code = generator.generate(
        [
            {'action': 'click', 'selector': 'id:login', 'description': 'clicar login'},
            {'action': 'input', 'selector': 'button.primary', 'value': 'BR'},
        ],
        start_url='https://example.com',
    )

    assert '# clicar login' in code
    assert 'Click    css=#login >> nth=0' in code
    assert 'Fill Text    button.primary    BR' in code