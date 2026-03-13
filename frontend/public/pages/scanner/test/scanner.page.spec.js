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
  deleteGeneratedTestService,
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
        feedback: 'Fix the login test',
        testIds: expect.any(Array)
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

  // ── loadExecuteProjects error ─────────────────────────────────────────────

  it('shows error toast when loadExecuteProjects fails', async () => {
    getProjects.mockRejectedValue(new Error('Network error'));
    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();
    expect(toast).toHaveBeenCalledWith('Network error', 'error');
  });

  // ── testsList click: download button ──────────────────────────────────────

  it('testsList download button opens tests download URL in new tab', async () => {
    const openMock = vi.fn();
    vi.stubGlobal('open', openMock);

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([
      { id: 5, file_path: 'tests/login.robot', created_at: '2024-01-01' }
    ]);

    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    document.querySelector('[data-test-download]').click();

    expect(openMock).toHaveBeenCalledWith('/tests/5/download', '_blank');
    vi.unstubAllGlobals();
  });

  // ── testsList click: area without any button ───────────────────────────────

  it('testsList click on plain content area does nothing', () => {
    initScannerPage({ onRecreateRequested: vi.fn() });
    document.getElementById('tests-list').innerHTML = '<div class="plain">text</div>';
    document
      .querySelector('#tests-list .plain')
      .dispatchEvent(new Event('click', { bubbles: true }));
    expect(toast).not.toHaveBeenCalled();
  });

  // ── testsList click: delete confirm cancel ────────────────────────────────

  it('testsList delete button does not call service when confirm is cancelled', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false));

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([
      { id: 5, file_path: 'tests/login.robot', created_at: '2024-01-01' }
    ]);
    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    document.querySelector('[data-test-delete]').click();

    await vi.waitFor(() => expect(deleteGeneratedTestService).not.toHaveBeenCalled());
    vi.unstubAllGlobals();
  });

  // ── testsList click: delete success ───────────────────────────────────────

  it('testsList delete button calls service and shows success toast', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([
      { id: 5, file_path: 'tests/login.robot', created_at: '2024-01-01' }
    ]);
    deleteGeneratedTestService.mockResolvedValue(undefined);

    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    getProjectGeneratedTests.mockResolvedValue([]);
    document.querySelector('[data-test-delete]').click();

    await vi.waitFor(() => expect(deleteGeneratedTestService).toHaveBeenCalledWith(5));
    expect(toast).toHaveBeenCalledWith('Teste excluido com sucesso!');
    vi.unstubAllGlobals();
  });

  // ── testsList click: delete error ─────────────────────────────────────────

  it('testsList delete button shows error toast when service throws', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([
      { id: 5, file_path: 'tests/login.robot', created_at: '2024-01-01' }
    ]);
    deleteGeneratedTestService.mockRejectedValue(new Error('Delete failed'));

    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    document.querySelector('[data-test-delete]').click();

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Delete failed', 'error'));
    vi.unstubAllGlobals();
  });

  // ── testsProjectSelect change ─────────────────────────────────────────────

  it('testsProjectSelect change loads generated tests for the selected project', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    getProjectGeneratedTests.mockResolvedValue([
      { id: 7, file_path: 'tests/new.robot', created_at: '2024-01-01' }
    ]);

    const select = document.getElementById('tests-project');
    select.value = '1';
    select.dispatchEvent(new Event('change'));

    await vi.waitFor(() =>
      expect(document.getElementById('tests-list').textContent).toContain('tests/new.robot')
    );
  });

  // ── loadExecuteTests error ────────────────────────────────────────────────

  it('loadExecuteTests shows error state when getProjectGeneratedTests fails', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    getProjectGeneratedTests.mockRejectedValue(new Error('fetch error'));

    const select = document.getElementById('execute-project');
    select.value = '1';
    select.dispatchEvent(new Event('change'));

    await vi.waitFor(() =>
      expect(document.getElementById('execute-test-list-check').textContent).toContain(
        'Erro ao carregar testes.'
      )
    );
  });

  // ── loadExecuteTests: no projectId hides selector ─────────────────────────

  it('loadExecuteTests hides test selector when projectId is falsy', async () => {
    initScannerPage({ onRecreateRequested: vi.fn() });
    document.getElementById('execute-test-selector').classList.remove('hidden');

    const select = document.getElementById('execute-project');
    select.value = '';
    select.dispatchEvent(new Event('change'));

    await vi.waitFor(() =>
      expect(document.getElementById('execute-test-selector').classList.contains('hidden')).toBe(
        true
      )
    );
  });

  // ── loadExecuteTests: empty tests list shows empty state ──────────────────

  it('loadExecuteTests shows empty state when project has no tests', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    const select = document.getElementById('execute-project');
    select.value = '1';
    select.dispatchEvent(new Event('change'));

    await vi.waitFor(() =>
      expect(document.getElementById('execute-test-list-check').textContent).toContain(
        'Nenhum teste gerado para este projeto.'
      )
    );
  });

  // ── renderTestCases ───────────────────────────────────────────────────────

  it('renderTestCases renders PASS, FAIL and SKIP test cases including messages', async () => {
    document.body.innerHTML += '<div id="execution-test-list"></div>';

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockResolvedValue({
      total_tests: 3,
      passed: 1,
      failed: 1,
      skipped: 1,
      error_output: null,
      test_cases: [
        { name: 'Test Pass', status: 'PASS', message: null },
        { name: 'Test Fail', status: 'FAIL', message: 'Something broke' },
        { name: 'Test Skip', status: 'SKIP', message: '' }
      ]
    });

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('execution-test-list').innerHTML).toContain('Test Pass')
    );
    expect(document.getElementById('execution-test-list').innerHTML).toContain('Test Fail');
    expect(document.getElementById('execution-test-list').innerHTML).toContain('Something broke');
    expect(document.getElementById('execution-test-list').innerHTML).toContain('Test Skip');
  });

  it('renderTestCases clears list when test_cases is empty array', async () => {
    const listEl = document.createElement('div');
    listEl.id = 'execution-test-list';
    listEl.innerHTML = '<p>old</p>';
    document.body.appendChild(listEl);

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockResolvedValue({
      total_tests: 2,
      passed: 2,
      failed: 0,
      skipped: 0,
      error_output: null,
      test_cases: []
    });

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    // Wait for the post-600ms stat update (distinguishes from resetExecutionResult's '0')
    await vi.waitFor(() => expect(document.getElementById('stat-total').textContent).toBe('2'));
    expect(document.getElementById('execution-test-list').innerHTML).toBe('');
  });

  // ── submit with error_output ──────────────────────────────────────────────

  it('submit shows error_output text in execution-error element', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockResolvedValue({
      total_tests: 1,
      passed: 0,
      failed: 1,
      skipped: 0,
      error_output: 'Robot execution error details',
      test_cases: []
    });

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => {
      expect(document.getElementById('execution-error').textContent).toBe(
        'Robot execution error details'
      );
      expect(document.getElementById('execution-error').style.display).toBe('block');
    });
  });

  // ── phase timeout callbacks ───────────────────────────────────────────────

  it('activates heal and run phases via setTimeout callbacks', async () => {
    vi.useFakeTimers();

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    let resolveExec;
    executeProjectTests.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveExec = () =>
            resolve({
              total_tests: 0,
              passed: 0,
              failed: 0,
              skipped: 0,
              error_output: null,
              test_cases: []
            });
        })
    );

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    // Use real timers for the loadExecuteProjects await
    vi.useRealTimers();
    await loadExecuteProjects();
    vi.useFakeTimers();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    // Advance past t1 (3000ms) to trigger the 'heal' phase callback
    await vi.advanceTimersByTimeAsync(3001);
    expect(document.querySelector('[data-phase="heal"]')?.className).toContain('gen-step--active');

    // Advance another 5001ms (total ~8002ms) to trigger the 'run' phase callback
    await vi.advanceTimersByTimeAsync(5001);
    expect(document.querySelector('[data-phase="run"]')?.className).toContain('gen-step--active');

    // Resolve execution and advance through the 600ms + 1500ms delays
    resolveExec();
    await vi.advanceTimersByTimeAsync(2200);

    vi.useRealTimers();
  });

  // ── loadGeneratedTests: testsList element missing (lines 129-130) ─────────

  it('loadGeneratedTests returns early when testsList element is absent', async () => {
    // Remove testsList before init so the captured variable is null inside the function
    document.getElementById('tests-list').remove();
    initScannerPage({ onRecreateRequested: vi.fn() });

    // Trigger loadGeneratedTests directly via the change event (bypasses loadTestsProjects guard)
    const select = document.getElementById('tests-project');
    select.value = '1';
    select.dispatchEvent(new Event('change'));

    await Promise.resolve();
    // loadGeneratedTests hit the !testsList early-return, so the service was never called
    expect(getProjectGeneratedTests).not.toHaveBeenCalled();
  });

  // ── loadGeneratedTests: falsy projectId (lines 133-135) ──────────────────

  it('loadGeneratedTests shows "select a project" message when projectId is falsy', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    initScannerPage({ onRecreateRequested: vi.fn() });

    // Trigger the change event with an empty value (falsy projectId)
    const select = document.getElementById('tests-project');
    select.value = '';
    select.dispatchEvent(new Event('change'));

    await vi.waitFor(() =>
      expect(document.getElementById('tests-list').innerHTML).toContain('Selecione um projeto')
    );
  });

  // ── loadGeneratedTests: catch block (lines 164-166) ───────────────────────

  it('loadGeneratedTests shows error state and toast when service throws', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockRejectedValue(new Error('fetch failed'));

    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();

    expect(document.getElementById('tests-list').innerHTML).toContain('Erro ao carregar testes');
    expect(toast).toHaveBeenCalledWith('fetch failed', 'error');
  });

  // ── loadTestsProjects: missing elements (lines 171-172) ──────────────────

  it('loadTestsProjects returns early when required DOM elements are absent', async () => {
    document.getElementById('tests-project').remove();
    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();
    expect(getProjects).not.toHaveBeenCalled();
  });

  // ── loadTestsProjects: empty projects list (lines 185-187) ───────────────

  it('loadTestsProjects shows empty state when no projects exist', async () => {
    getProjects.mockResolvedValue([]);
    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();
    expect(document.getElementById('tests-list').innerHTML).toContain(
      'Nenhum projeto criado ainda'
    );
  });

  // ── loadTestsProjects: catch block (lines 194-196) ────────────────────────

  it('loadTestsProjects shows error state and toast when getProjects throws', async () => {
    getProjects.mockRejectedValue(new Error('server error'));
    const { loadTestsProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadTestsProjects();
    expect(document.getElementById('tests-list').innerHTML).toContain('Erro ao carregar projetos');
    expect(toast).toHaveBeenCalledWith('server error', 'error');
  });

  // ── loadExecuteProjects: missing element (lines 201-202) ─────────────────

  it('loadExecuteProjects returns early when executeProjectSelect is absent', async () => {
    document.getElementById('execute-project').remove();
    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();
    expect(getProjects).not.toHaveBeenCalled();
  });

  // ── extractExecutionMessage: fallback when all error_output lines are blank (line 36) ──

  it('extractExecutionMessage returns fallback when error_output has only blank lines', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockResolvedValue({
      total_tests: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      error_output: '\n   \n   \n', // truthy but all lines are blank/whitespace
      test_cases: []
    });

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith('A execucao dos testes falhou.', 'error')
    );
  });

  // ── getHeadless: false branch when exec-headless is absent (line 84) ──────

  it('getHeadless returns true when exec-headless checkbox is absent', async () => {
    document.getElementById('exec-headless').remove();
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    executeProjectTests.mockResolvedValue({
      total_tests: 0,
      passed: 0,
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
    // Third arg: getHeadless() fallback returns true when element is absent
    expect(executeProjectTests.mock.calls[0][2]).toBe(true);
  });

  // ── getSelectedTestIds: ?. false branch when execute-test-list-check absent (line 88) ──

  it('getSelectedTestIds returns empty array when execute-test-list-check element is absent', async () => {
    document.getElementById('execute-test-list-check').remove();
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    executeProjectTests.mockResolvedValue({
      total_tests: 0,
      passed: 0,
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
    // Second arg: executeTestListCheck?.querySelectorAll(...) ?? [] → []
    expect(executeProjectTests.mock.calls[0][1]).toEqual([]);
  });

  // ── loadExecuteTests: returns early when executeTestSelector absent (line 224) ──

  it('loadExecuteTests returns early when execute-test-selector element is absent', async () => {
    document.getElementById('execute-test-selector').remove();
    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    const select = document.getElementById('execute-project');
    select.value = '1';
    select.dispatchEvent(new Event('change'));

    await Promise.resolve();
    // loadExecuteTests guard: !executeTestSelector = true → return without calling service
    expect(getProjectGeneratedTests).not.toHaveBeenCalled();
  });

  // ── buildExecTracker.activate: !el continue branch (line 320) ────────────

  it('buildExecTracker activate skips null phase element via continue', async () => {
    vi.useFakeTimers();

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);

    let resolveExec;
    executeProjectTests.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveExec = () =>
            resolve({
              total_tests: 0,
              passed: 0,
              failed: 0,
              skipped: 0,
              error_output: null,
              test_cases: []
            });
        })
    );

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    vi.useRealTimers();
    await loadExecuteProjects();
    vi.useFakeTimers();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    // Synchronous submit init is complete; buildExecTracker has set executionLoading.innerHTML.
    // Remove one phase element so getEl() returns null on the next activate() call.
    document.querySelector('[data-phase="prepare"]')?.remove();

    // Advance past t1 (3000ms) → tracker.activate('heal');
    // for-loop iterates: getEl('prepare') = null → continue  ← covers line 320
    await vi.advanceTimersByTimeAsync(3001);
    expect(document.querySelector('[data-phase="heal"]')?.className).toContain('gen-step--active');

    resolveExec();
    await vi.advanceTimersByTimeAsync(2200);
    vi.useRealTimers();
  });

  // ── renderTestCases: tc.status falsy branch (line 358) ───────────────────

  it('renderTestCases maps null status to skip class', async () => {
    document.body.innerHTML += '<div id="execution-test-list"></div>';

    getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
    getProjectGeneratedTests.mockResolvedValue([]);
    executeProjectTests.mockResolvedValue({
      total_tests: 1,
      passed: 0,
      failed: 0,
      skipped: 1,
      error_output: null,
      test_cases: [{ name: 'Unknown Status', status: null, message: null }]
    });

    const { loadExecuteProjects } = initScannerPage({ onRecreateRequested: vi.fn() });
    await loadExecuteProjects();

    document.getElementById('execute-project').value = '1';
    document
      .getElementById('execute-tests-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('execution-test-list').innerHTML).toContain('Unknown Status')
    );
    // null status → tc.status || '' → st = '' → cls = 'skip'
    expect(document.getElementById('execution-test-list').innerHTML).toContain(
      'exec-test-item--skip'
    );
  });
});
