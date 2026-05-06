import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  getAvailableAiModels: vi.fn().mockResolvedValue({ models: [] }),
  generateTestFromPrompt: vi.fn(),
  improveExistingGeneratedTest: vi.fn(),
  startVisualBuilderSession: vi.fn(),
  getVisualBuilderCapturedSteps: vi.fn(),
  deleteVisualBuilderCapturedStep: vi.fn(),
  updateVisualBuilderCapturedStep: vi.fn(),
  getProjectGeneratedTests: vi.fn().mockResolvedValue([]),
  getTestContent: vi.fn().mockResolvedValue(null),
}));
vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));

vi.mock('../../../utils/dom.js', async () => {
  const actual = await vi.importActual('../../../utils/dom.js');
  return { ...actual, loadTemplate: vi.fn().mockResolvedValue('') };
});

import { toast } from '../../../components/toast.js';
import {
  deleteVisualBuilderCapturedStep,
  generateTestFromPrompt,
  getAvailableAiModels,
  getProjectGeneratedTests,
  getProjects,
  getTestContent,
  getVisualBuilderCapturedSteps,
  improveExistingGeneratedTest,
  startVisualBuilderSession,
  updateVisualBuilderCapturedStep,
} from '../../../services/test.service.js';
import { initGeneratorPage, mount } from '../generator.page.js';

function buildDOM() {
  document.body.innerHTML = `
    <select id="test-project">
      <option value="">Selecione</option>
      <option value="1" data-url="https://demo.com">Demo</option>
      <option value="2" data-url="">Sem URL</option>
    </select>

    <div id="generation-status" class="hidden">
      <span id="generation-status-label"></span>
      <span id="generation-status-detail"></span>
      <span id="generation-status-timer">0s</span>
    </div>

    <div id="generated-result" class="hidden"></div>
    <code id="test-code"></code>
    <button id="copy-test-btn">Copy</button>
    <button id="download-test-btn" data-test-id="">Download</button>

    <form id="visual-builder-form">
      <input id="builder-url" type="url" />
      <textarea id="builder-prompt"></textarea>
      <select id="builder-llm-model"><option value="">Padrão do servidor</option></select>
      <button id="builder-llm-refresh-models-btn" type="button">Refresh Models</button>
      <select id="builder-llm-plan">
        <option value="balanced">Balanced</option>
        <option value="strict">Strict / Deterministic</option>
        <option value="exploratory">Exploratory</option>
      </select>
      <input id="builder-llm-temperature" type="number" value="0.2" />
      <input id="builder-llm-max-tokens" type="number" value="4096" />
      <textarea id="builder-llm-system-prompt"></textarea>
      <button id="builder-start-btn" type="submit">Start</button>
      <button id="builder-refresh-steps-btn" type="button">Refresh</button>
      <button id="builder-generate-btn" type="button">Generate</button>
    </form>

    <div id="builder-session-banner" class="hidden"><strong id="builder-session-id">-</strong></div>
    <div id="builder-steps-panel" class="hidden">
      <p id="builder-steps-summary"></p>
      <p id="builder-selected-step-summary" class="hidden"></p>
      <ul id="builder-steps-list"></ul>
    </div>
    <div id="builder-code-panel" class="hidden">
      <button id="builder-copy-code-btn">Copy Builder</button>
      <code id="builder-code"></code>
    </div>
  `;
}

function makeStore(extra = {}) {
  let state = { projects: [], activeProjectId: null, ...extra };
  return {
    getState: () => state,
    setState: (patch) => {
      state = { ...state, ...patch };
    },
  };
}

describe('generator page (test builder only)', () => {
  beforeEach(() => {
    buildDOM();
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.useRealTimers();
  });

  it('returns no-op functions when required DOM is missing', async () => {
    document.body.innerHTML = '';
    const page = initGeneratorPage({ store: makeStore() });
    await expect(page.loadProjectsDropdown()).resolves.toBeUndefined();
    await expect(page.generateFromExecutionFeedback(1, 'x')).resolves.toBeUndefined();
  });

  it('restores/saves builder prompt in localStorage', () => {
    localStorage.setItem('builder_prompt', 'saved objective');
    localStorage.setItem('builder_plan', 'strict');
    localStorage.setItem('builder_temperature', '0.5');
    localStorage.setItem('builder_max_tokens', '2048');
    localStorage.setItem('builder_system_prompt', 'custom system');
    initGeneratorPage({ store: makeStore() });

    const input = document.getElementById('builder-prompt');
    expect(input.value).toBe('saved objective');

    input.value = 'new objective';
    input.dispatchEvent(new Event('input'));
    expect(localStorage.getItem('builder_prompt')).toBe('new objective');
    expect(document.getElementById('builder-llm-plan').value).toBe('strict');
    expect(document.getElementById('builder-llm-temperature').value).toBe('0.5');
    expect(document.getElementById('builder-llm-max-tokens').value).toBe('2048');
    expect(document.getElementById('builder-llm-system-prompt').value).toBe('custom system');
  });

  it('loads available AI models and supports manual refresh', async () => {
    getAvailableAiModels.mockResolvedValue({
      models: [
        { id: 'gpt-5-mini', name: 'GPT-5 Mini' },
        { id: 'gpt-5', name: 'GPT-5' },
      ],
    });

    initGeneratorPage({ store: makeStore() });

    await vi.waitFor(() => expect(getAvailableAiModels).toHaveBeenCalledTimes(1));
    expect(document.getElementById('builder-llm-model').textContent).toContain('gpt-5-mini');

    document.getElementById('builder-llm-refresh-models-btn').click();
    await vi.waitFor(() => expect(getAvailableAiModels).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Modelos de IA atualizados.'));
  });

  it('loadProjectsDropdown populates select and syncs builder URL', async () => {
    getProjects.mockResolvedValue([
      { id: 1, name: 'Proj A', url: 'https://a.com' },
      { id: 2, name: 'Proj B', url: 'https://b.com' },
    ]);
    const page = initGeneratorPage({ store: makeStore({ activeProjectId: 2 }) });
    await page.loadProjectsDropdown();

    expect(document.getElementById('test-project').value).toBe('2');
    expect(document.getElementById('builder-url').value).toBe('https://b.com');
  });

  it('loadProjectsDropdown handles errors', async () => {
    getProjects.mockRejectedValue(new Error('API down'));
    const page = initGeneratorPage({ store: makeStore() });
    await page.loadProjectsDropdown();
    expect(toast).toHaveBeenCalledWith('API down', 'error');
  });

  it('updates active project and builder URL on project change', () => {
    const store = makeStore();
    getVisualBuilderCapturedSteps.mockResolvedValue({ session_id: null, steps: [] });
    initGeneratorPage({ store });

    const select = document.getElementById('test-project');
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    expect(store.getState().activeProjectId).toBe(1);
    expect(document.getElementById('builder-url').value).toBe('https://demo.com');
  });

  it('loads project steps when project is selected', async () => {
    getVisualBuilderCapturedSteps.mockResolvedValue({
      session_id: 'session-project-1',
      steps: [{ id: 4, step: 1, action: 'click', selector: '#project-step' }],
    });

    const store = makeStore();
    initGeneratorPage({ store });

    const select = document.getElementById('test-project');
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(getVisualBuilderCapturedSteps).toHaveBeenCalledWith(null, 1));
    expect(document.getElementById('builder-session-id').textContent).toBe('session-project-1');
    expect(document.getElementById('builder-steps-list').textContent).toContain('#project-step');
  });

  it('blocks start when no project selected', () => {
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    expect(toast).toHaveBeenCalledWith(
      'Selecione um projeto antes de iniciar captura visual.',
      'error'
    );
  });

  it('blocks start when selected project has no URL', () => {
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '2';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    expect(toast).toHaveBeenCalledWith(
      'Projeto sem URL. Selecione um projeto com URL válida.',
      'error'
    );
  });

  it('starts visual builder and exposes active session', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-1' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(startVisualBuilderSession).toHaveBeenCalledWith('https://demo.com', 1)
    );
    expect(document.getElementById('builder-session-banner').classList.contains('hidden')).toBe(
      false
    );
    expect(document.getElementById('builder-session-id').textContent).toBe('session-1');
  });

  it('handles start builder errors', async () => {
    startVisualBuilderSession.mockRejectedValue(new Error('cannot start'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('cannot start', 'error'));
  });

  it('refresh button requests captured steps and renders list', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-2' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ step: 1, type: 'click', selector: '#a' }],
    });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() => expect(getVisualBuilderCapturedSteps).toHaveBeenCalledWith('session-2'));
    expect(document.getElementById('builder-steps-list').textContent).toContain('#a');
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Steps atualizados com sucesso.'));
  });

  it('renders rich builder metadata and saves custom step name', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-9' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [
        {
          id: 91,
          step: 1,
          action: 'click',
          selector: '#login',
          step_name: 'Abrir login',
          description: 'Clique no botão principal',
          page_url: 'https://demo.com/login',
          page_title: 'Login',
          element_tag: 'button',
          element_text: 'Entrar',
        },
      ],
    });
    updateVisualBuilderCapturedStep.mockResolvedValue({ id: 91, step_name: 'Clicar em Entrar' });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.getElementById('builder-steps-list').textContent).toContain(
        'https://demo.com/login'
      )
    );

    const input = document.querySelector('.builder-step-name-input');
    input.value = 'Clicar em Entrar';
    document.querySelector('.builder-step-save-btn').click();

    await vi.waitFor(() =>
      expect(updateVisualBuilderCapturedStep).toHaveBeenCalledWith(91, {
        step_name: 'Clicar em Entrar',
      })
    );
  });

  it('deletes a captured step from the list', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-del' });
    getVisualBuilderCapturedSteps
      .mockResolvedValueOnce({
        steps: [
          { id: 31, step: 1, action: 'click', selector: '#del' },
          { id: 32, step: 2, action: 'click', selector: '#keep' },
        ],
      })
      .mockResolvedValueOnce({
        steps: [{ id: 32, step: 1, action: 'click', selector: '#keep' }],
      });
    deleteVisualBuilderCapturedStep.mockResolvedValue({ message: 'Step deleted', step_id: 31 });

    const confirmMock = vi.fn().mockReturnValue(true);
    vi.stubGlobal('confirm', confirmMock);

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.querySelectorAll('.builder-step-delete-btn').length).toBe(2)
    );

    document.querySelector('.builder-step-delete-btn[data-step-id="31"]').click();

    await vi.waitFor(() => expect(confirmMock).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(deleteVisualBuilderCapturedStep).toHaveBeenCalledWith(31));
    await vi.waitFor(() =>
      expect(document.getElementById('builder-steps-list').textContent).toContain('#keep')
    );
    expect(document.getElementById('builder-steps-list').textContent).not.toContain('#del');
    expect(toast).toHaveBeenCalledWith('Step apagado com sucesso.');

    vi.unstubAllGlobals();
  });

  it('refresh without session shows error path', () => {
    initGeneratorPage({ store: makeStore() });
    document.getElementById('builder-refresh-steps-btn').click();
    expect(toast).toHaveBeenCalledWith('Inicie uma sessão visual antes de buscar steps.', 'error');
  });

  it('generate button blocks when no session exists', () => {
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('builder-generate-btn').click();
    expect(toast).toHaveBeenCalledWith('Inicie uma sessão visual antes de gerar código.', 'error');
  });

  it('generate button blocks when no steps were captured', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-3' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-generate-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        'Nenhum step capturado. Interaja na tela antes de gerar o teste.',
        'error'
      )
    );
  });

  it('generate button builds prompt/context and renders generated code', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-4' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ step: 1, action: 'click', selector: '#login', description: 'clicar login' }],
    });
    generateTestFromPrompt.mockResolvedValue({ id: 33, content: '*** Test Cases ***\nBuilder' });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('builder-prompt').value = 'validar login';
    document.getElementById('builder-llm-model').innerHTML =
      '<option value="">Padrão</option><option value="gpt-5-mini">GPT-5 Mini</option>';
    document.getElementById('builder-llm-model').value = 'gpt-5-mini';
    document.getElementById('builder-llm-temperature').value = '0.4';
    document.getElementById('builder-llm-max-tokens').value = '3072';
    document.getElementById('builder-llm-system-prompt').value = 'foco em robustez';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-generate-btn').click();
    await vi.waitFor(() =>
      expect(generateTestFromPrompt).toHaveBeenCalledWith(
        expect.objectContaining({
          projectId: 1,
          prompt: expect.stringContaining('validar login'),
          context: expect.stringContaining('Step selecionado para geracao'),
          model: 'gpt-5-mini',
          temperature: 0.4,
          maxTokens: 3072,
          systemPrompt: 'foco em robustez',
        })
      )
    );
    expect(document.getElementById('builder-code').textContent).toContain('*** Test Cases ***');
    expect(document.getElementById('test-code').textContent).toContain('Builder');
    expect(document.getElementById('download-test-btn').dataset.testId).toBe('33');
    expect(document.getElementById('generated-result').classList.contains('hidden')).toBe(false);
    expect(toast).toHaveBeenCalledWith(expect.stringContaining('Gerando teste para o step:'));
    expect(toast).toHaveBeenCalledWith(
      expect.stringContaining('Arquivo .robot gerado para o step:')
    );
  });

  it('generate button uses default prompt and handles generation errors', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-5' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ step: 1, action: 'click', selector: '#x' }],
    });
    generateTestFromPrompt.mockRejectedValue(new Error('llm error'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('builder-prompt').value = 'a';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-generate-btn').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('llm error', 'error'));
    expect(generateTestFromPrompt).toHaveBeenCalledWith(
      expect.objectContaining({
        prompt: expect.stringContaining('Gerar teste Robot Framework para o step selecionado:'),
      })
    );
  });

  it('generates directly from step action button', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-8' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [
        { id: 11, step: 1, action: 'click', selector: '#login', step_name: 'Abrir login' },
        { id: 12, step: 2, action: 'input', selector: '#user', step_name: 'Preencher usuario' },
      ],
    });
    generateTestFromPrompt.mockResolvedValue({ id: 55, content: '*** Test Cases ***\nStep' });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.getElementById('builder-steps-list').textContent).toContain(
        'Gerar .robot deste step'
      )
    );

    document.querySelector('.builder-step-generate-btn').click();

    await vi.waitFor(() =>
      expect(generateTestFromPrompt).toHaveBeenCalledWith(
        expect.objectContaining({
          context: expect.stringContaining('step=1'),
        })
      )
    );
    expect(document.querySelector('.builder-step-generate-btn').textContent).toContain(
      'Teste ja gerado'
    );
    expect(document.querySelector('.builder-step-generate-btn').className).toContain(
      'builder-step-generate-btn--generated'
    );
    expect(document.getElementById('builder-generate-btn').textContent).toContain(
      'Step Selecionado Ja Gerado'
    );
    expect(document.getElementById('download-test-btn').dataset.testId).toBe('55');
  });

  it('plan selection updates system prompt and persists llm settings', () => {
    initGeneratorPage({ store: makeStore() });

    const plan = document.getElementById('builder-llm-plan');
    const systemPrompt = document.getElementById('builder-llm-system-prompt');
    const temperature = document.getElementById('builder-llm-temperature');
    const maxTokens = document.getElementById('builder-llm-max-tokens');

    plan.value = 'strict';
    plan.dispatchEvent(new Event('change'));
    expect(localStorage.getItem('builder_plan')).toBe('strict');
    expect(systemPrompt.value.length).toBeGreaterThan(0);

    temperature.value = '0.6';
    temperature.dispatchEvent(new Event('input'));
    maxTokens.value = '8192';
    maxTokens.dispatchEvent(new Event('input'));
    systemPrompt.value = 'prompt customizado';
    systemPrompt.dispatchEvent(new Event('input'));

    expect(localStorage.getItem('builder_temperature')).toBe('0.6');
    expect(localStorage.getItem('builder_max_tokens')).toBe('8192');
    expect(localStorage.getItem('builder_system_prompt')).toBe('prompt customizado');
  });

  it('updates generation status detail after 30s while generating', async () => {
    vi.useFakeTimers();
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-6' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ step: 1, action: 'click', selector: '#x' }],
    });
    let resolveGenerate;
    generateTestFromPrompt.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveGenerate = resolve;
        })
    );

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-generate-btn').click();
    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(false)
    );
    vi.advanceTimersByTime(30000);
    expect(document.getElementById('generation-status-timer').textContent).toBe('30s');
    expect(document.getElementById('generation-status-detail').textContent).toContain(
      'Aguardando resposta do LLM'
    );

    resolveGenerate({ id: 1, content: 'ok' });
    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(true)
    );
  });

  it('polls builder steps in background when session is active', async () => {
    vi.useFakeTimers();
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-7' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(2600);
    expect(getVisualBuilderCapturedSteps).toHaveBeenCalledWith('session-7');
  });

  it('copies generated code and builder code', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-code').textContent = 'robot code';
    document.getElementById('builder-code').textContent = 'builder code';

    document.getElementById('copy-test-btn').click();
    document.getElementById('builder-copy-code-btn').click();

    await vi.waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
    expect(toast).toHaveBeenCalledWith('Código copiado!');
    expect(toast).toHaveBeenCalledWith('Código Robot copiado!');
    vi.unstubAllGlobals();
  });

  it('downloads generated file only when test id exists', () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    initGeneratorPage({ store: makeStore() });

    document.getElementById('download-test-btn').dataset.testId = '';
    document.getElementById('download-test-btn').click();
    expect(openMock).not.toHaveBeenCalled();

    document.getElementById('download-test-btn').dataset.testId = '99';
    document.getElementById('download-test-btn').click();
    expect(openMock).toHaveBeenCalledWith('/tests/99/download', '_blank');
    vi.unstubAllGlobals();
  });

  it('generateFromExecutionFeedback uses provided test id first', async () => {
    getTestContent.mockResolvedValueOnce('*** Test Cases ***\nOriginal');
    improveExistingGeneratedTest.mockResolvedValue({ content: '*** Test Cases ***\nFixed' });

    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(1, 'feedback', [42]);

    expect(getTestContent).toHaveBeenCalledWith(42);
    expect(improveExistingGeneratedTest).toHaveBeenCalledWith(
      42,
      '*** Test Cases ***\nOriginal',
      'feedback'
    );
    expect(document.getElementById('download-test-btn').dataset.testId).toBe('42');
  });

  it('generateFromExecutionFeedback falls back to most recent test when ids are missing', async () => {
    getProjectGeneratedTests.mockResolvedValueOnce([{ id: 7 }]);
    getTestContent.mockResolvedValueOnce('*** Test Cases ***\nExisting');
    improveExistingGeneratedTest.mockResolvedValue({ content: null });

    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(2, 'fallback feedback', []);

    expect(getProjectGeneratedTests).toHaveBeenCalledWith(2);
    expect(getTestContent).toHaveBeenCalledWith(7);
    expect(improveExistingGeneratedTest).toHaveBeenCalledWith(
      7,
      '*** Test Cases ***\nExisting',
      'fallback feedback'
    );
    expect(document.getElementById('test-code').textContent).toBe('');
    expect(document.getElementById('download-test-btn').dataset.testId).toBe('7');
  });

  it('mount returns page API', async () => {
    const root = document.createElement('div');
    document.body.appendChild(root);
    const page = await mount(root, { store: makeStore() });
    expect(typeof page.loadProjectsDropdown).toBe('function');
    expect(typeof page.generateFromExecutionFeedback).toBe('function');
    root.remove();
  });

  // ---------------------------------------------------------------------------
  // loadAiModelsDropdown coverage (lines 175-179, 183)
  // ---------------------------------------------------------------------------

  it('loadAiModelsDropdown restores previously stored model when found in list', async () => {
    localStorage.setItem('builder_model', 'gpt-5');
    getAvailableAiModels.mockResolvedValue({
      models: [
        { id: 'gpt-4', name: 'GPT-4' },
        { id: 'gpt-5', name: 'GPT-5' },
      ],
    });
    initGeneratorPage({ store: makeStore() });
    await vi.waitFor(() =>
      expect(document.getElementById('builder-llm-model').value).toBe('gpt-5')
    );
  });

  it('loadAiModelsDropdown shows error toast when getAvailableAiModels throws', async () => {
    getAvailableAiModels.mockRejectedValue(new Error('models unavailable'));
    initGeneratorPage({ store: makeStore() });
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('models unavailable', 'error'));
  });

  it('loadAiModelsDropdown shows fallback toast when error has no message', async () => {
    getAvailableAiModels.mockRejectedValue({});
    initGeneratorPage({ store: makeStore() });
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith('Falha ao carregar modelos de IA', 'error')
    );
  });

  it('llmModelSelect change event persists model to localStorage', () => {
    initGeneratorPage({ store: makeStore() });
    const select = document.getElementById('builder-llm-model');
    select.innerHTML += '<option value="gpt-5">GPT-5</option>';
    select.value = 'gpt-5';
    select.dispatchEvent(new Event('change'));
    expect(localStorage.getItem('builder_model')).toBe('gpt-5');
  });

  // ---------------------------------------------------------------------------
  // syncBuilderUrlWithSelectedProject guard (lines 193-194)
  // ---------------------------------------------------------------------------

  it('syncBuilderUrlWithSelectedProject returns early when builder-url is missing', () => {
    document.getElementById('builder-url').remove();
    const store = makeStore();
    getVisualBuilderCapturedSteps.mockResolvedValue({ session_id: null, steps: [] });
    initGeneratorPage({ store });
    const select = document.getElementById('test-project');
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    // no crash = guard executed correctly
  });

  // ---------------------------------------------------------------------------
  // DOM guard tests (lines 236-237, 300-301, 320-321)
  // ---------------------------------------------------------------------------

  it('updateSelectedStepSummary guard: returns early when element is missing', async () => {
    document.getElementById('builder-selected-step-summary').remove();
    startVisualBuilderSession.mockResolvedValue({ session_id: 'sx' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ id: 1, step: 1, action: 'click', selector: '#x' }],
    });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));
  });

  it('updateBuilderGenerateButtonState guard: returns early when element is missing', async () => {
    document.getElementById('builder-generate-btn').remove();
    startVisualBuilderSession.mockResolvedValue({ session_id: 'sy' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ id: 2, step: 1, action: 'click', selector: '#y' }],
    });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));
  });

  it('renderBuilderSteps guard: returns early when panel elements are missing', async () => {
    document.getElementById('builder-steps-panel').remove();
    startVisualBuilderSession.mockResolvedValue({ session_id: 'sz' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));
  });

  // ---------------------------------------------------------------------------
  // startBuilderPoll coverage (lines 447-449, 454-455)
  // ---------------------------------------------------------------------------

  it('poll stops gracefully when session is cleared while polling', async () => {
    vi.useFakeTimers();
    startVisualBuilderSession.mockResolvedValue({ session_id: 'poll-stop' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ session_id: null, steps: [] });

    const store = makeStore();
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(2600);
    await Promise.resolve();
    document.getElementById('test-project').value = '';
    document.getElementById('test-project').dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();
    vi.advanceTimersByTime(2600);
    await Promise.resolve();
    expect(getVisualBuilderCapturedSteps).toHaveBeenCalled();
  });

  it('poll silently ignores transient getVisualBuilderCapturedSteps errors', async () => {
    vi.useFakeTimers();
    startVisualBuilderSession.mockResolvedValue({ session_id: 'poll-err' });
    getVisualBuilderCapturedSteps
      .mockResolvedValueOnce({ steps: [] })
      .mockRejectedValue(new Error('transient'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    vi.advanceTimersByTime(2600);
    await Promise.resolve();
    vi.advanceTimersByTime(2600);
    await Promise.resolve();

    document.getElementById('test-project').value = '';
    document.getElementById('test-project').dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(toast).not.toHaveBeenCalledWith('transient', 'error');
  });

  // ---------------------------------------------------------------------------
  // saveBuilderStepName: input not found (lines 481-482)
  // ---------------------------------------------------------------------------

  it('save button: clicking with valid stepId but missing name input does not crash', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'save-guard' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    const list = document.getElementById('builder-steps-list');
    list.innerHTML =
      '<li><button class="builder-step-save-btn" data-step-id="999">Save</button></li>';
    document.querySelector('.builder-step-save-btn').click();
    await vi.waitFor(() => expect(updateVisualBuilderCapturedStep).not.toHaveBeenCalled());
  });

  // ---------------------------------------------------------------------------
  // generateFromBuilderStep: no project selected (lines 565-567)
  // ---------------------------------------------------------------------------

  it('generate btn: throws when no project is selected during generation', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'no-proj' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ id: 5, step: 1, action: 'click', selector: '#a' }],
    });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.getElementById('builder-steps-list').textContent).toContain('#a')
    );

    document.getElementById('test-project').value = '';
    document.getElementById('builder-generate-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        'Selecione um projeto antes de gerar o teste visual.',
        'error'
      )
    );
  });

  // ---------------------------------------------------------------------------
  // loadBuilderStepsForProject: null projectId (lines 658-661)
  // ---------------------------------------------------------------------------

  it('loadBuilderStepsForProject clears session when projectId is null', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'clr' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    const store = makeStore();
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('test-project').value = '';
    document.getElementById('test-project').dispatchEvent(new Event('change', { bubbles: true }));
    await vi.waitFor(() =>
      expect(document.getElementById('builder-session-banner').classList.contains('hidden')).toBe(
        true
      )
    );
  });

  // ---------------------------------------------------------------------------
  // generateFromExecutionFeedback: no tests fallback (lines 699-704)
  // ---------------------------------------------------------------------------

  it('generateFromExecutionFeedback falls back to generateTestFromPrompt when no tests', async () => {
    getProjectGeneratedTests.mockResolvedValueOnce([]);
    generateTestFromPrompt.mockResolvedValue({ id: 20, content: '*** Test Cases ***\nFallback' });

    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(3, 'feedback no tests', []);

    expect(generateTestFromPrompt).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: 3,
        prompt: 'Recriar teste com base no feedback da execucao (falhas/erros).',
        context: 'feedback no tests',
      })
    );
    expect(toast).toHaveBeenCalledWith('Teste corrigido com base nos erros da execucao!');
  });

  // ---------------------------------------------------------------------------
  // projectSelect change: error path (lines 729-730)
  // ---------------------------------------------------------------------------

  it('projectSelect change shows error toast when loadBuilderStepsForProject throws', async () => {
    getVisualBuilderCapturedSteps.mockRejectedValue(new Error('steps failed'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('test-project').dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('steps failed', 'error'));
  });

  // ---------------------------------------------------------------------------
  // builderRefreshStepsBtn: error path (lines 784-785)
  // ---------------------------------------------------------------------------

  it('builderRefreshStepsBtn shows error toast when refreshBuilderSteps throws', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval').mockImplementation(() => 1);
    startVisualBuilderSession.mockResolvedValue({ session_id: 'ref-err' });
    getVisualBuilderCapturedSteps.mockRejectedValue(new Error('refresh failed'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('refresh failed', 'error'));
    setIntervalSpy.mockRestore();
  });

  // ---------------------------------------------------------------------------
  // builderStepsList click: save button edge cases (lines 797-799, 805)
  // ---------------------------------------------------------------------------

  it('save button with stepId=0 shows invalid step toast', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'save-inv' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    const list = document.getElementById('builder-steps-list');
    list.innerHTML =
      '<li><button class="builder-step-save-btn" data-step-id="0">Save</button></li>';
    document.querySelector('.builder-step-save-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith('Step inválido para atualização.', 'error')
    );
  });

  it('save button shows error toast when saveBuilderStepName throws', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'save-throw' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });
    updateVisualBuilderCapturedStep.mockRejectedValue(new Error('save error'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    const list = document.getElementById('builder-steps-list');
    list.innerHTML = `
      <li>
        <input class="builder-step-name-input" data-step-id="50" value="My Step" />
        <button class="builder-step-save-btn" data-step-id="50">Save</button>
      </li>`;
    document.querySelector('.builder-step-save-btn').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('save error', 'error'));
  });

  // ---------------------------------------------------------------------------
  // builderStepsList click: delete button edge cases (lines 816-818, 826-827, 833)
  // ---------------------------------------------------------------------------

  it('delete button with stepId=0 shows invalid step toast', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'del-inv' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    const list = document.getElementById('builder-steps-list');
    list.innerHTML =
      '<li><button class="builder-step-delete-btn" data-step-id="0">Delete</button></li>';
    document.querySelector('.builder-step-delete-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith('Step inválido para exclusão.', 'error')
    );
  });

  it('delete button: confirm returns false cancels deletion', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'del-cancel' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    const list = document.getElementById('builder-steps-list');
    list.innerHTML =
      '<li><button class="builder-step-delete-btn" data-step-id="10">Delete</button></li>';
    document.querySelector('.builder-step-delete-btn').click();
    await vi.waitFor(() => expect(globalThis.confirm).toHaveBeenCalledTimes(1));
    expect(deleteVisualBuilderCapturedStep).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('delete button shows error toast when deleteBuilderStep throws', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'del-throw' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    deleteVisualBuilderCapturedStep.mockRejectedValue(new Error('delete error'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    const list = document.getElementById('builder-steps-list');
    list.innerHTML =
      '<li><button class="builder-step-delete-btn" data-step-id="11">Delete</button></li>';
    document.querySelector('.builder-step-delete-btn').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('delete error', 'error'));
    vi.unstubAllGlobals();
  });

  // ---------------------------------------------------------------------------
  // builderStepsList click: generate button edge cases (lines 844-846, 854-856, 859-860)
  // ---------------------------------------------------------------------------

  it('inline generate button with empty stepKey shows invalid step toast', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'gen-inv' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    const list = document.getElementById('builder-steps-list');
    list.innerHTML =
      '<li><button class="builder-step-generate-btn" data-step-key="">Generate</button></li>';
    document.querySelector('.builder-step-generate-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith('Step inválido para geração.', 'error')
    );
  });

  it('inline generate button shows not-found toast when step disappears after refresh', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'gen-miss' });
    getVisualBuilderCapturedSteps
      .mockResolvedValueOnce({ steps: [{ id: 7, step: 1, action: 'click', selector: '#z' }] })
      .mockResolvedValueOnce({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.getElementById('builder-steps-list').textContent).toContain('#z')
    );

    document.querySelector('.builder-step-generate-btn[data-step-key="id:7"]').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        'Step selecionado não encontrado após atualização.',
        'error'
      )
    );
  });

  it('inline generate button shows error toast when generateFromBuilderStep throws', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'gen-throw' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ id: 8, step: 1, action: 'click', selector: '#q' }],
    });
    generateTestFromPrompt.mockRejectedValueOnce(new Error('generate failed'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.getElementById('builder-steps-list').textContent).toContain('#q')
    );

    document.querySelector('.builder-step-generate-btn[data-step-key="id:8"]').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('generate failed', 'error'));
  });

  // ---------------------------------------------------------------------------
  // builderStepsList click: step item selection (lines 867-875)
  // ---------------------------------------------------------------------------

  it('clicking a step item updates the selected step', async () => {
    initGeneratorPage({ store: makeStore() });
    const list = document.getElementById('builder-steps-list');
    list.innerHTML = '<li class="builder-step-item" data-step-key="id:22">Step 22</li>';
    const secondItem = document.querySelector('.builder-step-item[data-step-key="id:22"]');
    secondItem.click();
    expect(document.getElementById('builder-steps-list').children.length).toBe(0);
  });

  // ---------------------------------------------------------------------------
  // builderStepsList change event: radio selection (lines 879-894)
  // ---------------------------------------------------------------------------

  it('radio change event updates selected step', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'radio-select' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [
        { id: 31, step: 1, action: 'click', selector: '#r1' },
        { id: 32, step: 2, action: 'click', selector: '#r2' },
      ],
    });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.querySelectorAll('.builder-step-select-input').length).toBe(2)
    );

    const radio = document.querySelector('.builder-step-select-input[data-step-key="id:32"]');
    radio.dispatchEvent(new Event('change', { bubbles: true }));
    await vi.waitFor(() => {
      const item = document.querySelector('.builder-step-item[data-step-key="id:32"]');
      expect(item.classList.contains('is-selected')).toBe(true);
    });
  });

  // ---------------------------------------------------------------------------
  // builderStepsList keydown: Enter saves step name (lines 898-917)
  // ---------------------------------------------------------------------------

  it('pressing Enter on a step name input saves the step name', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'keydown-save' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ id: 41, step: 1, action: 'click', selector: '#k' }],
    });
    updateVisualBuilderCapturedStep.mockResolvedValue({ id: 41, step_name: 'New Name' });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.querySelector('.builder-step-name-input')).not.toBeNull()
    );

    const input = document.querySelector('.builder-step-name-input[data-step-id="41"]');
    input.value = 'New Name';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    await vi.waitFor(() =>
      expect(updateVisualBuilderCapturedStep).toHaveBeenCalledWith(41, { step_name: 'New Name' })
    );
  });

  it('pressing Enter on name input shows error toast when save throws', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'keydown-err' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ id: 42, step: 1, action: 'click', selector: '#ke' }],
    });
    updateVisualBuilderCapturedStep.mockRejectedValue(new Error('keydown save error'));

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.querySelector('.builder-step-name-input[data-step-id="42"]')).not.toBeNull()
    );

    const input = document.querySelector('.builder-step-name-input[data-step-id="42"]');
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('keydown save error', 'error'));
  });

  it('pressing non-Enter key on name input does nothing', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'keydown-noop' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ id: 43, step: 1, action: 'click', selector: '#kn' }],
    });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() =>
      expect(document.querySelector('.builder-step-name-input[data-step-id="43"]')).not.toBeNull()
    );

    const input = document.querySelector('.builder-step-name-input[data-step-id="43"]');
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(updateVisualBuilderCapturedStep).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------------------
  // builderGenerateBtn click: no selected step (lines 936-938)
  // ---------------------------------------------------------------------------

  it('generate button shows toast when no steps available after refresh', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'no-sel' });
    getVisualBuilderCapturedSteps.mockResolvedValue({ steps: [] });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));

    document.getElementById('builder-generate-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        'Nenhum step capturado. Interaja na tela antes de gerar o teste.',
        'error'
      )
    );
  });
});
