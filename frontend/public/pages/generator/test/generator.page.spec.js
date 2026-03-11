import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  generateTestFromPrompt: vi.fn()
}));
vi.mock('../../../services/scan.service.js', () => ({ runProjectScan: vi.fn() }));
vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));

import { toast } from '../../../components/toast.js';
import { runProjectScan } from '../../../services/scan.service.js';
import { generateTestFromPrompt, getProjects } from '../../../services/test.service.js';
import { initGeneratorPage } from '../generator.page.js';

function buildDOM() {
  document.body.innerHTML = `
    <form id="generate-test-form">
      <select id="test-project">
        <option value="">Selecione</option>
        <option value="1" data-url="https://demo.com">Demo</option>
      </select>
      <textarea id="test-prompt"></textarea>
      <textarea id="test-context"></textarea>
      <button id="scan-page-btn">Scan</button>
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
    <div id="generated-result" class="hidden"></div>
    <code id="test-code"></code>
  `;
}

function makeStore(extra = {}) {
  let s = { projects: [], lastScanResult: null, activeProjectId: null, ...extra };
  return {
    getState: () => s,
    setState: (p) => {
      s = { ...s, ...p };
    }
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

  it('toasts error when loadProjectsDropdown fails', async () => {
    getProjects.mockRejectedValue(new Error('API down'));
    const page = initGeneratorPage({ store: makeStore() });
    await page.loadProjectsDropdown();
    expect(toast).toHaveBeenCalledWith('API down', 'error');
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
    expect(toast).toHaveBeenCalledWith('Novo teste gerado com base no feedback da execução!');
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
      'Projeto sem URL. Edite/crie um projeto com URL válida.',
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
});
