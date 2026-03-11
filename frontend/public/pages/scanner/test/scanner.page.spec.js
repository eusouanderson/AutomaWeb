import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ── mocks ────────────────────────────────────────────────────────────────────
vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  getProjectGeneratedTests: vi.fn(),
  executeProjectTests: vi.fn(),
  deleteGeneratedTestService: vi.fn()
}));

vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));
vi.mock('../../../utils/helpers.js', () => ({
  formatDate: vi.fn((v) => (v ? String(v) : '-'))
}));

// ── imports ───────────────────────────────────────────────────────────────────
import { toast } from '../../../components/toast.js';
import {
  executeProjectTests,
  getProjectGeneratedTests,
  getProjects
} from '../../../services/test.service.js';
import { initScannerPage } from '../scanner.page.js';

// ── DOM fixture builder ───────────────────────────────────────────────────────
function buildDOM() {
  document.body.innerHTML = `
    <select id="tests-project"></select>
    <div id="tests-list"></div>

    <form id="execute-tests-form">
      <select id="execute-project"></select>
      <button type="submit">Run</button>
    </form>

    <div id="execution-loading" class="hidden"></div>
    <div id="execution-result" style="display:none"></div>
    <div id="execution-error" style="display:none"></div>

    <span id="stat-total">0</span>
    <span id="stat-passed">0</span>
    <span id="stat-failed">0</span>
    <span id="stat-skipped">0</span>

    <button id="view-report-btn" data-report-path=""></button>
    <button id="view-robot-report-btn" data-report-path=""></button>
    <button id="view-log-btn" data-log-path=""></button>

    <div id="recreate-panel" class="hidden"></div>
    <button id="recreate-test-btn" data-project-id=""></button>
    <textarea id="execution-feedback"></textarea>

    <div id="execute-test-selector" class="hidden"></div>
    <div id="execute-test-list-check"></div>
    <button id="exec-select-all"></button>
    <button id="exec-deselect-all"></button>
    <input type="checkbox" id="exec-headless" checked />
  `;
}

// ── tests ─────────────────────────────────────────────────────────────────────
describe('scanner page – initScannerPage', () => {
  beforeEach(() => {
    localStorage.clear();
    buildDOM();
    vi.clearAllMocks();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('restores feedback textarea from localStorage', () => {
    localStorage.setItem('scanner_feedback', 'previous feedback');
    initScannerPage({ onRecreateRequested: vi.fn() });
    expect(document.getElementById('execution-feedback').value).toBe('previous feedback');
  });

  it('saves feedback textarea to localStorage on input', () => {
    initScannerPage({ onRecreateRequested: vi.fn() });
    const textarea = document.getElementById('execution-feedback');
    textarea.value = 'new feedback';
    textarea.dispatchEvent(new Event('input'));
    expect(localStorage.getItem('scanner_feedback')).toBe('new feedback');
  });

  it('loads projects into tests-project select', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj A' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    const options = document.querySelectorAll('#tests-project option');
    expect(options.length).toBeGreaterThan(1);
    const texts = [...options].map((o) => o.textContent);
    expect(texts).toContain('Proj A');
  });

  it('loads projects into execute-project select', async () => {
    getProjects.mockResolvedValue([{ id: 2, name: 'Proj B', test_directory: 'tests/' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    const options = document.querySelectorAll('#execute-project option');
    const texts = [...options].map((o) => o.textContent);
    expect(texts.some((t) => t.includes('Proj B'))).toBe(true);
  });

  it('shows test list items after loadTestsProjects', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'MyProj' }]);
    getProjectGeneratedTests.mockResolvedValue([
      { id: 10, file_path: 'tests/login.robot', created_at: '2024-01-01' }
    ]);

    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    expect(document.getElementById('tests-list').textContent).toContain('tests/login.robot');
  });

  it('calls executeProjectTests on execute form submit', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockResolvedValue({
      total_tests: 1,
      passed: 1,
      failed: 0,
      skipped: 0,
      error_output: null
    });

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(executeProjectTests).toHaveBeenCalledTimes(1));
  });

  it('displays stat values after successful execution', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockResolvedValue({
      total_tests: 3,
      passed: 2,
      failed: 1,
      skipped: 0,
      error_output: null
    });

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(document.getElementById('stat-total').textContent).toBe('3'));
    expect(document.getElementById('stat-passed').textContent).toBe('2');
    expect(document.getElementById('stat-failed').textContent).toBe('1');
  });

  it('shows error toast when execution fails', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockRejectedValue(new Error('Execution failed'));

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Execution failed', 'error'));
  });

  it('select-all checks all exec-test-check boxes', () => {
    document.getElementById('execute-test-list-check').innerHTML = `
      <input type="checkbox" class="exec-test-check" value="1" />
      <input type="checkbox" class="exec-test-check" value="2" />
    `;
    initScannerPage({ onRecreateRequested: vi.fn() });
    document.getElementById('exec-select-all').click();
    const checked = document.querySelectorAll('.exec-test-check:checked');
    expect(checked.length).toBe(2);
  });

  it('deselect-all unchecks all exec-test-check boxes', () => {
    document.getElementById('execute-test-list-check').innerHTML = `
      <input type="checkbox" class="exec-test-check" value="1" checked />
      <input type="checkbox" class="exec-test-check" value="2" checked />
    `;
    initScannerPage({ onRecreateRequested: vi.fn() });
    document.getElementById('exec-deselect-all').click();
    const checked = document.querySelectorAll('.exec-test-check:checked');
    expect(checked.length).toBe(0);
  });

  it('reportButton opens report path in a new tab', () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    initScannerPage({ onRecreateRequested: vi.fn() });
    const btn = document.getElementById('view-report-btn');
    btn.dataset.reportPath = '/reports/index.html';
    btn.click();

    expect(openMock).toHaveBeenCalledWith('/reports/index.html', '_blank');
    vi.unstubAllGlobals();
  });

  it('reportButton does not open when path is empty', () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    initScannerPage({ onRecreateRequested: vi.fn() });
    document.getElementById('view-report-btn').click();

    expect(openMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('robotReportButton opens robot report path in a new tab', () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    initScannerPage({ onRecreateRequested: vi.fn() });
    const btn = document.getElementById('view-robot-report-btn');
    btn.dataset.reportPath = '/robot/report.html';
    btn.click();

    expect(openMock).toHaveBeenCalledWith('/robot/report.html', '_blank');
    vi.unstubAllGlobals();
  });

  it('logButton opens log path in a new tab', () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    initScannerPage({ onRecreateRequested: vi.fn() });
    const btn = document.getElementById('view-log-btn');
    btn.dataset.logPath = '/logs/log.html';
    btn.click();

    expect(openMock).toHaveBeenCalledWith('/logs/log.html', '_blank');
    vi.unstubAllGlobals();
  });

  it('executeProjectSelect change resets result and loads tests', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    // Populate a test so the list renders
    getProjectGeneratedTests.mockResolvedValue([
      { id: 5, file_path: 'tests/login.robot', created_at: '2024-01-01' }
    ]);

    const select = document.getElementById('execute-project');
    select.value = '1';
    select.dispatchEvent(new Event('change'));

    await vi.waitFor(() => expect(document.getElementById('stat-total').textContent).toBe('0'));
    await vi.waitFor(() =>
      expect(document.getElementById('execute-test-selector').classList.contains('hidden')).toBe(
        false
      )
    );
  });

  it('recreateButton toasts error when projectId is not set', async () => {
    initScannerPage({ onRecreateRequested: vi.fn() });
    // dataset.projectId is '' (falsy) by default from buildDOM
    document.getElementById('recreate-test-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        'Nao foi possivel identificar o projeto da execucao.',
        'error'
      )
    );
  });

  it('recreateButton toasts error when feedback is empty', async () => {
    initScannerPage({ onRecreateRequested: vi.fn() });
    document.getElementById('recreate-test-btn').dataset.projectId = '42';
    document.getElementById('execution-feedback').value = '   ';
    document.getElementById('recreate-test-btn').click();
    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith('Adicione um feedback para enviar a IA.', 'error')
    );
  });

  it('recreateButton calls onRecreateRequested with projectId and feedback', async () => {
    const onRecreate = vi.fn().mockResolvedValue(undefined);
    initScannerPage({ onRecreateRequested: onRecreate });

    document.getElementById('recreate-test-btn').dataset.projectId = '7';
    document.getElementById('execution-feedback').value = 'Fix the login test';
    document.getElementById('recreate-test-btn').click();

    await vi.waitFor(() =>
      expect(onRecreate).toHaveBeenCalledWith({
        projectId: 7,
        feedback: 'Fix the login test'
      })
    );
  });

  it('recreateButton shows error toast when onRecreateRequested throws', async () => {
    const onRecreate = vi.fn().mockRejectedValue(new Error('Recreate failed'));
    initScannerPage({ onRecreateRequested: onRecreate });

    document.getElementById('recreate-test-btn').dataset.projectId = '7';
    document.getElementById('execution-feedback').value = 'some feedback';
    document.getElementById('recreate-test-btn').click();

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Recreate failed', 'error'));
  });
});
