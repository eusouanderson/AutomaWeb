import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  generateTestFromPrompt: vi.fn(),
  startVisualBuilderSession: vi.fn(),
  getVisualBuilderCapturedSteps: vi.fn(),
  getProjectGeneratedTests: vi.fn().mockResolvedValue([]),
  getTestContent: vi.fn().mockResolvedValue(null),
}));
vi.mock('../../../services/scan.service.js', () => ({ runProjectScan: vi.fn() }));
vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));

vi.mock('../../../utils/dom.js', async () => {
  const actual = await vi.importActual('../../../utils/dom.js');
  return { ...actual, loadTemplate: vi.fn().mockResolvedValue('') };
});

import { toast } from '../../../components/toast.js';
import { runProjectScan } from '../../../services/scan.service.js';
import {
  generateTestFromPrompt,
  getProjectGeneratedTests,
  getProjects,
  getTestContent,
  getVisualBuilderCapturedSteps,
  startVisualBuilderSession,
} from '../../../services/test.service.js';
import { initGeneratorPage, mount } from '../generator.page.js';

function buildDOM() {
  document.body.innerHTML = `
    <form id="generate-test-form">
      <select id="test-project">
        <option value="">Selecione</option>
        <option value="1" data-url="https://demo.com">Demo</option>
      </select>
      <textarea id="test-prompt"></textarea>
      <textarea id="test-context"></textarea>
      <div id="gen-scan-cache-notice" class="hidden"><span id="gen-scan-cache-date"></span></div>
      <button id="gen-rescan-btn">Refazer scan</button>
      <button id="scan-page-btn">Scan</button>
      <button id="generate-submit-btn" type="submit">Gerar Teste</button>
      <button id="copy-test-btn">Copy</button>
      <button id="download-test-btn" data-test-id="">Download</button>
    </form>
    <div id="scan-panel" class="hidden"></div>
    <div id="scan-summary" class="hidden"></div>
    <div id="scan-live-status" class="hidden"></div>
    <div id="scan-ready-message" class="hidden"></div>
    <div id="scan-progress"></div>
    <span id="scan-title">-</span>
    <span id="scan-total">0</span>
    <span id="scan-types">-</span>
    <div id="generation-status" class="hidden">
      <span class="generation-status-spinner"></span>
      <div class="generation-status-body">
        <span id="generation-status-label"></span>
        <span id="generation-status-detail"></span>
      </div>
      <span id="generation-status-timer">0s</span>
    </div>
    <div id="generated-result" class="hidden"></div>
    <div id="generation-parts" class="hidden">
      <p id="generation-parts-summary"></p>
      <ul id="generation-parts-list"></ul>
    </div>
    <code id="test-code"></code>
    <form id="visual-builder-form">
      <input id="builder-url" type="url" />
      <textarea id="builder-prompt"></textarea>
      <button id="builder-start-btn" type="submit">Start Builder</button>
      <button id="builder-refresh-steps-btn" type="button">Refresh Steps</button>
      <button id="builder-generate-btn" type="button">Generate Code</button>
    </form>
    <div id="builder-session-banner" class="hidden"><strong id="builder-session-id">-</strong></div>
    <div id="builder-steps-panel" class="hidden">
      <p id="builder-steps-summary"></p>
      <ul id="builder-steps-list"></ul>
    </div>
    <div id="builder-code-panel" class="hidden">
      <button id="builder-copy-code-btn">Copy Builder Code</button>
      <code id="builder-code"></code>
    </div>
  `;
}

function makeStore(extra = {}) {
  let s = { projects: [], lastScanResult: null, activeProjectId: null, ...extra };
  return {
    getState: () => s,
    setState: (p) => {
      s = { ...s, ...p };
    },
  };
}

describe('generator page (legacy) – initGeneratorPage', () => {
  beforeEach(() => {
    buildDOM();
    localStorage.clear();
    vi.clearAllMocks();
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  // ── early return ──────────────────────────────────────────────────────────

  it('returns no-op functions when DOM is missing', async () => {
    document.body.innerHTML = '';
    const page = initGeneratorPage({ store: makeStore() });
    await expect(page.loadProjectsDropdown()).resolves.toBeUndefined();
    await expect(page.generateFromExecutionFeedback(1, 'x')).resolves.toBeUndefined();
  });

  // ── localStorage memory ───────────────────────────────────────────────────

  it('restores prompt and context from localStorage', () => {
    localStorage.setItem('gen_prompt', 'saved prompt');
    localStorage.setItem('gen_context', 'saved context');
    initGeneratorPage({ store: makeStore() });
    expect(document.getElementById('test-prompt').value).toBe('saved prompt');
    expect(document.getElementById('test-context').value).toBe('saved context');
  });

  it('saves prompt to localStorage on input', () => {
    initGeneratorPage({ store: makeStore() });
    const el = document.getElementById('test-prompt');
    el.value = 'typed';
    el.dispatchEvent(new Event('input'));
    expect(localStorage.getItem('gen_prompt')).toBe('typed');
  });

  it('saves context to localStorage on input', () => {
    initGeneratorPage({ store: makeStore() });
    const el = document.getElementById('test-context');
    el.value = 'ctx';
    el.dispatchEvent(new Event('input'));
    expect(localStorage.getItem('gen_context')).toBe('ctx');
  });

  // ── loadProjectsDropdown ──────────────────────────────────────────────────

  it('populates projects select from API', async () => {
    getProjects.mockResolvedValue([{ id: 2, name: 'Proj B', url: 'https://b.com' }]);
    const page = initGeneratorPage({ store: makeStore() });
    await page.loadProjectsDropdown();
    const opts = document.querySelectorAll('#test-project option');
    expect([...opts].map((o) => o.textContent)).toContain('Proj B');
  });

  it('fills visual builder URL from active selected project after loading projects', async () => {
    getProjects.mockResolvedValue([
      { id: 1, name: 'Proj A', url: 'https://a.com' },
      { id: 2, name: 'Proj B', url: 'https://b.com' },
    ]);
    const page = initGeneratorPage({ store: makeStore({ activeProjectId: 2 }) });
    await page.loadProjectsDropdown();

    expect(document.getElementById('builder-url').value).toBe('https://b.com');
  });

  it('toasts error when loadProjectsDropdown fails', async () => {
    getProjects.mockRejectedValue(new Error('API down'));
    const page = initGeneratorPage({ store: makeStore() });
    await page.loadProjectsDropdown();
    expect(toast).toHaveBeenCalledWith('API down', 'error');
  });

  it('selects active project from store when loading projects dropdown', async () => {
    getProjects.mockResolvedValue([
      { id: 1, name: 'Proj A', url: 'https://a.com' },
      { id: 2, name: 'Proj B', url: 'https://b.com' },
    ]);
    const page = initGeneratorPage({ store: makeStore({ activeProjectId: 2 }) });
    await page.loadProjectsDropdown();
    expect(document.getElementById('test-project').value).toBe('2');
  });

  // ── generateFromExecutionFeedback ─────────────────────────────────────────

  it('fills code element and shows result after generateFromExecutionFeedback', async () => {
    generateTestFromPrompt.mockResolvedValue({ id: 7, content: '*** Tests ***' });
    const store = makeStore();
    const page = initGeneratorPage({ store });
    await page.generateFromExecutionFeedback(1, 'some feedback');
    expect(document.getElementById('test-code').textContent).toBe('*** Tests ***');
    expect(document.getElementById('generated-result').classList.contains('hidden')).toBe(false);
  });

  it('shows success toast after generateFromExecutionFeedback', async () => {
    generateTestFromPrompt.mockResolvedValue({ id: 8, content: '' });
    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(1, 'fb');
    expect(toast).toHaveBeenCalledWith('Teste corrigido com base nos erros da execucao!');
  });

  // ── form submit ───────────────────────────────────────────────────────────

  it('toasts error when scan was not run before submitting', () => {
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    expect(toast).toHaveBeenCalledWith('Execute o scan da página antes de gerar o teste.', 'error');
  });

  it('calls generateTestFromPrompt when scan result is available', async () => {
    generateTestFromPrompt.mockResolvedValue({ id: 9, content: '*** Settings ***' });
    const store = makeStore({ lastScanResult: { title: 'x' }, activeProjectId: 1 });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document.getElementById('test-prompt').value = 'Login flow';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(generateTestFromPrompt).toHaveBeenCalledTimes(1));
    expect(generateTestFromPrompt).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: 1, prompt: 'Login flow' })
    );
  });

  it('shows generated result after successful submit', async () => {
    generateTestFromPrompt.mockResolvedValue({ id: 10, content: '*** Test ***' });
    const store = makeStore({ lastScanResult: { title: 'x' }, activeProjectId: 1 });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() =>
      expect(document.getElementById('generated-result').classList.contains('hidden')).toBe(false)
    );
    expect(document.getElementById('test-code').textContent).toBe('*** Test ***');
  });

  it('renders chunk parts summary when API returns chunk metadata', async () => {
    generateTestFromPrompt.mockResolvedValue({
      id: 11,
      content: '*** Test ***',
      generation_strategy: 'chunked',
      chunk_count: 2,
      chunk_target_chars: 1200,
      chunk_parts: [
        { index: 1, approx_chars: 900, keys: ['title', 'buttons'] },
        { index: 2, approx_chars: 850, keys: ['forms'] },
      ],
    });
    const store = makeStore({ lastScanResult: { title: 'x' }, activeProjectId: 1 });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('generation-parts').classList.contains('hidden')).toBe(false)
    );
    expect(document.getElementById('generation-parts-summary').textContent).toContain(
      'consolidado em 1 arquivo .robot'
    );
    expect(document.getElementById('generation-parts-list').textContent).toContain('Parte 1');
    expect(document.getElementById('generation-parts-list').textContent).toContain(
      'title, buttons'
    );
  });

  it('hides chunk parts summary for non-chunked generation', async () => {
    generateTestFromPrompt.mockResolvedValue({
      id: 12,
      content: '*** Test ***',
      generation_strategy: 'single',
    });
    const store = makeStore({ lastScanResult: { title: 'x' }, activeProjectId: 1 });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(generateTestFromPrompt).toHaveBeenCalledTimes(1));
    expect(document.getElementById('generation-parts').classList.contains('hidden')).toBe(true);
  });

  it('toasts error when generate fails on submit', async () => {
    generateTestFromPrompt.mockRejectedValue(new Error('AI error'));
    const store = makeStore({ lastScanResult: { title: 'x' }, activeProjectId: 1 });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('AI error', 'error'));
  });

  it('starts visual builder and shows active session', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-1' });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(startVisualBuilderSession).toHaveBeenCalledWith('https://demo.com')
    );
    expect(document.getElementById('builder-session-banner').classList.contains('hidden')).toBe(
      false
    );
  });

  it('refreshes visual builder steps list', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-1' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ step: 1, type: 'click', selector: '#login' }],
    });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));
    document.getElementById('builder-refresh-steps-btn').click();
    await vi.waitFor(() => expect(getVisualBuilderCapturedSteps).toHaveBeenCalledWith('session-1'));
    expect(document.getElementById('builder-steps-list').textContent).toContain('#login');
  });

  it('generates visual builder code and renders output', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-1' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ step: 1, action: 'click', selector: '#login', description: 'Clicar login' }],
    });
    generateTestFromPrompt.mockResolvedValue({ id: 88, content: '*** Test Cases ***\nVisual' });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));
    document.getElementById('builder-generate-btn').click();

    await vi.waitFor(() =>
      expect(generateTestFromPrompt).toHaveBeenCalledWith(
        expect.objectContaining({
          projectId: 1,
          prompt: expect.stringContaining('Gerar teste Robot Framework'),
          context: expect.stringContaining('Elementos testaveis capturados'),
        })
      )
    );
    expect(document.getElementById('builder-code-panel').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('builder-code').textContent).toContain('*** Test Cases ***');
    expect(document.getElementById('download-test-btn').dataset.testId).toBe('88');
  });

  it('forwards optional builder prompt when generating visual builder code', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-1' });
    getVisualBuilderCapturedSteps.mockResolvedValue({
      steps: [{ step: 1, action: 'click', selector: '#login' }],
    });
    generateTestFromPrompt.mockResolvedValue({ id: 89, content: 'ok' });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('visual-builder-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(startVisualBuilderSession).toHaveBeenCalledTimes(1));
    document.getElementById('builder-prompt').value = 'validar login';
    document.getElementById('builder-generate-btn').click();

    await vi.waitFor(() =>
      expect(generateTestFromPrompt).toHaveBeenCalledWith(
        expect.objectContaining({ projectId: 1, prompt: 'validar login' })
      )
    );
  });

  it('shows error when trying to generate visual test with no captured steps', async () => {
    startVisualBuilderSession.mockResolvedValue({ session_id: 'session-1' });
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

  // ── scan button ───────────────────────────────────────────────────────────

  it('toasts error when scan button clicked without selecting a project', () => {
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '';
    document.getElementById('scan-page-btn').click();
    expect(toast).toHaveBeenCalledWith('Selecione um projeto antes de escanear.', 'error');
  });

  it('toasts error when selected project has no URL', () => {
    document.body.querySelector('[value="1"]')?.removeAttribute('data-url');
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    expect(toast).toHaveBeenCalledWith(
      'Projeto sem URL. Selecione um projeto com URL válida.',
      'error'
    );
  });

  it('calls runProjectScan when scan button clicked with valid project', async () => {
    runProjectScan.mockResolvedValue({ title: 'P', total_elements: 3, summary: {} });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() => expect(runProjectScan).toHaveBeenCalledTimes(1));
  });

  it('shows scan summary after successful scan', async () => {
    runProjectScan.mockResolvedValue({ title: 'My Page', total_elements: 5, summary: { btn: 5 } });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() =>
      expect(document.getElementById('scan-title').textContent).toBe('My Page')
    );
    expect(document.getElementById('scan-total').textContent).toBe('5');
  });

  it('toasts error when scan fails', async () => {
    runProjectScan.mockRejectedValue(new Error('Scan failed'));
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Scan failed', 'error'));
  });

  // ── project select change resets scan panel ───────────────────────────────

  it('resets scan panel on project select change', () => {
    initGeneratorPage({ store: makeStore() });
    document.getElementById('scan-panel').classList.remove('hidden');
    document.getElementById('test-project').dispatchEvent(new Event('change', { bubbles: true }));
    expect(document.getElementById('scan-panel').classList.contains('hidden')).toBe(true);
  });

  it('updates visual builder URL when project selection changes', () => {
    initGeneratorPage({ store: makeStore() });
    const projectSelect = document.getElementById('test-project');
    projectSelect.value = '1';
    projectSelect.dispatchEvent(new Event('change', { bubbles: true }));

    expect(document.getElementById('builder-url').value).toBe('https://demo.com');
  });

  // ── appendScanProgress: early return when scanProgress absent (lines 71-72) ─

  it('appendScanProgress returns early when scan-progress element is absent', async () => {
    document.getElementById('scan-progress').remove();
    runProjectScan.mockResolvedValue({ title: 'T', total_elements: 1, summary: {} });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    // scan proceeds without throwing despite missing scanProgress
    await vi.waitFor(() => expect(runProjectScan).toHaveBeenCalledTimes(1));
  });

  // ── isScanning guard: second click ignored (lines 117-118) ────────────────

  it('ignores scan button click while already scanning', async () => {
    let resolvesScan;
    runProjectScan.mockImplementation(
      () =>
        new Promise((res) => {
          resolvesScan = res;
        })
    );
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';

    // First click: starts the scan; synchronously sets isScanning=true and disabled=true
    document.getElementById('scan-page-btn').click();

    // .click() is a no-op on a disabled button in jsdom — use dispatchEvent to bypass
    // and exercise the isScanning early-return branch (lines 117-118)
    document
      .getElementById('scan-page-btn')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }));

    await Promise.resolve();
    expect(runProjectScan).toHaveBeenCalledTimes(1);
    resolvesScan({ title: 'T', total_elements: 0, summary: {} });
  });

  // ── onError callback (lines 146-148) ──────────────────────────────────────

  it('invokes onError callback when scan service calls it', async () => {
    runProjectScan.mockImplementation((_url, _projectId, { onError }) => {
      onError('element not found');
      return Promise.resolve(null);
    });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('element not found', 'error'));
    expect(document.getElementById('scan-progress').textContent).toContain(
      'Erro: element not found'
    );
  });

  it('uses fallback toast message when onError called with empty message', async () => {
    runProjectScan.mockImplementation((_url, _projectId, { onError }) => {
      onError('');
      return Promise.resolve(null);
    });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Erro no scan', 'error'));
  });

  // ── copy button (lines 216-217) ────────────────────────────────────────────

  it('copy button writes code to clipboard and shows toast', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-code').textContent = '*** Test Cases ***';
    document.getElementById('copy-test-btn').click();

    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith('*** Test Cases ***'));
    expect(toast).toHaveBeenCalledWith('Código copiado!');
    vi.unstubAllGlobals();
  });

  // ── download button (lines 221-225) ───────────────────────────────────────

  it('download button opens download URL when testId is set', () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    initGeneratorPage({ store: makeStore() });
    document.getElementById('download-test-btn').dataset.testId = '42';
    document.getElementById('download-test-btn').click();

    expect(openMock).toHaveBeenCalledWith('/tests/42/download', '_blank');
    vi.unstubAllGlobals();
  });

  it('download button returns early when testId is empty', () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    initGeneratorPage({ store: makeStore() });
    document.getElementById('download-test-btn').dataset.testId = '';
    document.getElementById('download-test-btn').click();

    expect(openMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  // ── loadProjectsDropdown: project.url || '' false branch (line 91) ────────

  it('renders empty data-url when project has no url', async () => {
    getProjects.mockResolvedValue([{ id: 5, name: 'No URL', url: undefined }]);
    const page = initGeneratorPage({ store: makeStore() });
    await page.loadProjectsDropdown();
    const opt = document.querySelector('#test-project option[value="5"]');
    expect(opt?.dataset?.url).toBe('');
  });

  // ── generateFromExecutionFeedback: result.content || '' false branch (line 108) ─

  it('uses empty string for code when result.content is falsy', async () => {
    generateTestFromPrompt.mockResolvedValue({ id: 9, content: null });
    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(1, 'feedback');
    expect(document.getElementById('test-code').textContent).toBe('');
  });

  // ── generateFromExecutionFeedback: result.id || '' false branch (line 108 area) ─

  it('uses empty string for testId when result.id is falsy', async () => {
    generateTestFromPrompt.mockResolvedValue({ id: null, content: 'code' });
    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(1, 'feedback');
    expect(document.getElementById('download-test-btn').dataset.testId).toBe('');
  });

  // ── scan result: title || '-' false branch (line 159) ─────────────────────

  it('shows "-" for scan title when result has no title', async () => {
    runProjectScan.mockResolvedValue({ title: '', total_elements: 3, summary: { btn: 3 } });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() => expect(document.getElementById('scan-title').textContent).toBe('-'));
  });

  // ── scan result: typeSummary || '-' false branch (line 166) ───────────────

  it('shows "-" for scan types when summary is empty', async () => {
    runProjectScan.mockResolvedValue({ title: 'T', total_elements: 0, summary: {} });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() => expect(document.getElementById('scan-types').textContent).toBe('-'));
  });

  // ── form submit: result.content || '' and result.id || '' (lines 206-208) ─

  it('handles null result.content and result.id gracefully on form submit', async () => {
    generateTestFromPrompt.mockResolvedValue({ id: null, content: null });
    const store = makeStore({ lastScanResult: { title: 'x' }, activeProjectId: 1 });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(document.getElementById('test-code').textContent).toBe(''));
    expect(document.getElementById('download-test-btn').dataset.testId).toBe('');
  });

  // ── scan result: result.summary || {} right-side branch (line 166) ─────────

  it('shows "-" for scan types when summary is null', async () => {
    runProjectScan.mockResolvedValue({ title: 'T', total_elements: 0, summary: null });
    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-project').value = '1';
    document.getElementById('scan-page-btn').click();
    await vi.waitFor(() => expect(document.getElementById('scan-types').textContent).toBe('-'));
  });

  // ── copyButton: codeElement.textContent || '' false branch (line 216) ─────

  it('copy button writes empty string when code element is empty', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    initGeneratorPage({ store: makeStore() });
    document.getElementById('test-code').textContent = '';
    document.getElementById('copy-test-btn').click();

    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith(''));
    vi.unstubAllGlobals();
  });

  // ── mount (lines 13-17) ───────────────────────────────────────────────────

  it('mount loads the template and returns a page with loadProjectsDropdown', async () => {
    const root = document.createElement('div');
    document.body.appendChild(root);
    const page = await mount(root, { store: makeStore() });
    expect(typeof page.loadProjectsDropdown).toBe('function');
    expect(typeof page.generateFromExecutionFeedback).toBe('function');
    root.remove();
  });

  // ── genRescanBtn click (line 83) ──────────────────────────────────────────

  it('genRescanBtn click sets forceRescan flag and updates button text and class', () => {
    initGeneratorPage({ store: makeStore() });
    const btn = document.getElementById('gen-rescan-btn');
    btn.click();
    expect(btn.textContent).toBe('↻ Scan será refeito');
    expect(btn.classList.contains('btn-warning')).toBe(true);
  });

  // ── generateFromExecutionFeedback: testIds branch (lines 143-145) ─────────

  it('generateFromExecutionFeedback loads content from testIds when provided', async () => {
    getTestContent.mockResolvedValueOnce('*** Test Cases ***\nOriginal');
    generateTestFromPrompt.mockResolvedValue({ id: 50, content: '*** Test Cases ***\nFixed' });
    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(1, 'fix this', [42]);
    expect(getTestContent).toHaveBeenCalledWith(42);
    expect(generateTestFromPrompt).toHaveBeenCalledWith(
      expect.objectContaining({ context: expect.stringContaining('fix this') })
    );
  });

  // ── generateFromExecutionFeedback: fallback to project tests (lines 151-152)

  it('generateFromExecutionFeedback falls back to first project test when no testIds', async () => {
    getProjectGeneratedTests.mockResolvedValueOnce([{ id: 7 }]);
    getTestContent.mockResolvedValueOnce('*** Test Cases ***\nExisting');
    generateTestFromPrompt.mockResolvedValue({ id: 51, content: '*** Test Cases ***\nImproved' });
    const page = initGeneratorPage({ store: makeStore() });
    await page.generateFromExecutionFeedback(1, 'feedback text', []);
    expect(getProjectGeneratedTests).toHaveBeenCalledWith(1);
    expect(getTestContent).toHaveBeenCalledWith(7);
  });

  // ── generation status panel ────────────────────────────────────────────────

  it('shows generation-status panel and disables submit button while generating', async () => {
    let resolveGenerate;
    generateTestFromPrompt.mockImplementation(
      () =>
        new Promise((res) => {
          resolveGenerate = res;
        })
    );
    const store = makeStore({
      lastScanResult: { title: 'x', total_elements: 50 },
      activeProjectId: 1,
    });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document.getElementById('test-prompt').value = 'Teste login';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(false)
    );
    expect(document.getElementById('generate-submit-btn').disabled).toBe(true);
    expect(document.getElementById('generate-submit-btn').textContent).toBe('Gerando...');

    resolveGenerate({ id: 99, content: '*** Test Cases ***' });
    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(true)
    );
    expect(document.getElementById('generate-submit-btn').disabled).toBe(false);
    expect(document.getElementById('generate-submit-btn').textContent).toBe('Gerar Teste');
  });

  it('hides generation-status panel and re-enables button on generation error', async () => {
    generateTestFromPrompt.mockRejectedValue(new Error('LLM error'));
    const store = makeStore({ lastScanResult: { title: 'x' }, activeProjectId: 1 });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document.getElementById('test-prompt').value = 'Teste';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(true)
    );
    expect(document.getElementById('generate-submit-btn').disabled).toBe(false);
    expect(toast).toHaveBeenCalledWith('LLM error', 'error');
  });

  it('shows multi-part estimate in detail when element count is high', async () => {
    let resolveGenerate;
    generateTestFromPrompt.mockImplementation(
      () =>
        new Promise((res) => {
          resolveGenerate = res;
        })
    );
    // 96 elements → estimateChunks = ceil(96/48) = 2
    const store = makeStore({
      lastScanResult: { title: 'x', total_elements: 96 },
      activeProjectId: 1,
    });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document.getElementById('test-prompt').value = 'Teste';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(false)
    );
    expect(document.getElementById('generation-status-detail').textContent).toContain(
      'parte(s) a enviar'
    );
    resolveGenerate({ id: 100, content: '' });
  });

  it('updates generation status detail after 30 seconds elapsed', async () => {
    vi.useFakeTimers();
    let resolveGenerate;
    generateTestFromPrompt.mockImplementation(
      () =>
        new Promise((res) => {
          resolveGenerate = res;
        })
    );

    const store = makeStore({
      lastScanResult: { title: 'x', total_elements: 10 },
      activeProjectId: 1,
    });
    initGeneratorPage({ store });
    document.getElementById('test-project').value = '1';
    document.getElementById('test-prompt').value = 'Teste';
    document
      .getElementById('generate-test-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(false)
    );

    vi.advanceTimersByTime(30000);
    expect(document.getElementById('generation-status-timer').textContent).toBe('30s');
    expect(document.getElementById('generation-status-detail').textContent).toContain(
      'Aguardando resposta do LLM'
    );

    resolveGenerate({ id: 101, content: 'ok' });
    await vi.waitFor(() =>
      expect(document.getElementById('generation-status').classList.contains('hidden')).toBe(true)
    );
    vi.useRealTimers();
  });
});
