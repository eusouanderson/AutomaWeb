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
});
