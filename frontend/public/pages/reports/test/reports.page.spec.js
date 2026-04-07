import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  getProjectExecutions: vi.fn(),
}));
vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));
vi.mock('../../../utils/helpers.js', () => ({
  escapeHtml: (v) => String(v ?? ''),
  formatDate: (v) => (v ? String(v) : '-'),
}));

vi.mock('../../../utils/dom.js', async () => {
  const actual = await vi.importActual('../../../utils/dom.js');
  return { ...actual, loadTemplate: vi.fn().mockResolvedValue('') };
});

import { toast } from '../../../components/toast.js';
import { getProjectExecutions, getProjects } from '../../../services/test.service.js';
import { initReportsPage, mount } from '../reports.page.js';

function buildDOM() {
  document.body.innerHTML = `
    <select id="reports-project">
      <option value="">Selecione um projeto...</option>
    </select>
    <div id="reports-list"></div>
  `;
}

function makeStore(state = {}) {
  let s = { projects: [], ...state };
  return {
    getState: () => s,
    setState: (p) => {
      s = { ...s, ...p };
    },
  };
}

describe('reports page – initReportsPage', () => {
  beforeEach(() => {
    buildDOM();
    vi.clearAllMocks();
    vi.stubGlobal('open', vi.fn());
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  // ── early return ──────────────────────────────────────────────────────────

  it('returns a no-op when DOM is missing', async () => {
    document.body.innerHTML = '';
    const page = initReportsPage({ store: makeStore() });
    await expect(page.loadReportsProjects()).resolves.toBeUndefined();
  });

  // ── loadReportsProjects ───────────────────────────────────────────────────

  it('populates select from store when projects already loaded', async () => {
    const store = makeStore({ projects: [{ id: 1, name: 'Cached' }] });
    const page = initReportsPage({ store });
    await page.loadReportsProjects();
    const opts = document.querySelectorAll('#reports-project option');
    expect([...opts].map((o) => o.textContent)).toContain('Cached');
  });

  it('fetches projects from API when store is empty', async () => {
    getProjects.mockResolvedValue([{ id: 2, name: 'Fresh' }]);
    const page = initReportsPage({ store: makeStore() });
    await page.loadReportsProjects();
    expect(getProjects).toHaveBeenCalledTimes(1);
    const opts = document.querySelectorAll('#reports-project option');
    expect([...opts].map((o) => o.textContent)).toContain('Fresh');
  });

  it('shows placeholder message in reports list after load', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'P' }]);
    const page = initReportsPage({ store: makeStore() });
    await page.loadReportsProjects();
    expect(document.getElementById('reports-list').textContent).toContain('Selecione um projeto');
  });

  it('auto-loads executions when store has active project id', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 20,
        status: 'completed',
        total_tests: 1,
        passed: 1,
        failed: 0,
        skipped: 0,
        created_at: '2024',
      },
    ]);
    const page = initReportsPage({
      store: makeStore({ projects: [{ id: 4, name: 'Auto' }], activeProjectId: 4 }),
    });

    await page.loadReportsProjects();

    expect(document.getElementById('reports-project').value).toBe('4');
    expect(getProjectExecutions).toHaveBeenCalledWith(4);
  });

  it('toasts error when loadReportsProjects fails', async () => {
    getProjects.mockRejectedValue(new Error('Fetch fail'));
    const page = initReportsPage({ store: makeStore() });
    await page.loadReportsProjects();
    expect(toast).toHaveBeenCalledWith('Fetch fail', 'error');
  });

  // ── project select change ─────────────────────────────────────────────────

  it('loads executions when a project is selected', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 10,
        status: 'completed',
        total_tests: 2,
        passed: 2,
        failed: 0,
        skipped: 0,
        created_at: '2024',
      },
    ]);
    initReportsPage({ store: makeStore() });

    // Inject an option and select it
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '3';
    opt.textContent = 'Proj C';
    select.appendChild(opt);
    select.value = '3';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(getProjectExecutions).toHaveBeenCalledWith(3));
  });

  it('shows empty state when value 0 is selected', () => {
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    select.value = '';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    expect(document.getElementById('reports-list').textContent).toContain('Selecione um projeto');
  });

  it('renders execution stats in reports list', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 1,
        status: 'completed',
        total_tests: 5,
        passed: 4,
        failed: 1,
        skipped: 0,
        created_at: '2024',
      },
    ]);
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '1';
    select.appendChild(opt);
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('reports-list').textContent).toContain('5')
    );
    expect(document.getElementById('reports-list').textContent).toContain('4');
  });

  it('shows empty state when no executions exist', async () => {
    getProjectExecutions.mockResolvedValue([]);
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '1';
    select.appendChild(opt);
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() =>
      expect(document.getElementById('reports-list').textContent).toContain('Nenhuma execução')
    );
  });

  it('shows error state and toasts when execution load fails', async () => {
    getProjectExecutions.mockRejectedValue(new Error('DB error'));
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '1';
    select.appendChild(opt);
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('DB error', 'error'));
    expect(document.getElementById('reports-list').textContent).toContain('Erro');
  });

  // ── open button ───────────────────────────────────────────────────────────

  it('calls window.open when a [data-open] button is clicked', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 1,
        status: 'completed',
        total_tests: 1,
        passed: 1,
        failed: 0,
        skipped: 0,
        created_at: '2024',
        mkdocs_index: '/reports/1/index.html',
        report_file: null,
        log_file: null,
      },
    ]);
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '1';
    select.appendChild(opt);
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(document.querySelector('[data-open]')).not.toBeNull());
    document.querySelector('[data-open]')?.click();
    expect(globalThis.open).toHaveBeenCalledWith('/reports/1/index.html', '_blank');
  });

  // ── report_file and log_file buttons rendered (lines 61-62 true branches) ─

  it('renders report_file and log_file buttons when present', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 2,
        status: 'completed',
        total_tests: 1,
        passed: 1,
        failed: 0,
        skipped: 0,
        created_at: '2024',
        mkdocs_index: null,
        report_file: '/reports/2/report.html',
        log_file: '/reports/2/log.html',
      },
    ]);
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '2';
    select.appendChild(opt);
    select.value = '2';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(document.querySelectorAll('[data-open]').length).toBe(2));

    const buttons = [...document.querySelectorAll('[data-open]')];
    const paths = buttons.map((b) => b.dataset.open);
    expect(paths).toContain('/reports/2/report.html');
    expect(paths).toContain('/reports/2/log.html');
  });

  // ── error_output details block rendered (line 60 true branch) ────────────

  it('renders error details block when execution has error_output', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 3,
        status: 'failed',
        total_tests: 1,
        passed: 0,
        failed: 1,
        skipped: 0,
        created_at: '2024',
        error_output: 'Robot error: something went wrong',
        mkdocs_index: null,
        report_file: null,
        log_file: null,
      },
    ]);
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '3';
    select.appendChild(opt);
    select.value = '3';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(document.querySelector('.report-error-details')).not.toBeNull());
    expect(document.querySelector('.report-error-pre').textContent).toContain(
      'Robot error: something went wrong'
    );
  });

  // ── statusBadge: unknown status fallback (line 19 || right side) ──────────

  it('renders unknown status as a badge with the raw status label', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 4,
        status: 'pending',
        total_tests: 0,
        passed: 0,
        failed: 0,
        skipped: 0,
        created_at: '2024',
        error_output: null,
        mkdocs_index: null,
        report_file: null,
        log_file: null,
      },
    ]);
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '4';
    select.appendChild(opt);
    select.value = '4';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(document.querySelector('.exec-badge')).not.toBeNull());
    expect(document.querySelector('.exec-badge').textContent).toBe('pending');
  });

  // ── renderExecutions: ?? 0 fallback for null stats (lines 42-54) ─────────

  it('renders 0 for null total_tests, passed, failed, skipped values', async () => {
    getProjectExecutions.mockResolvedValue([
      {
        id: 5,
        status: 'completed',
        total_tests: null,
        passed: null,
        failed: null,
        skipped: null,
        created_at: '2024',
        error_output: null,
        mkdocs_index: null,
        report_file: null,
        log_file: null,
      },
    ]);
    initReportsPage({ store: makeStore() });
    const select = document.getElementById('reports-project');
    const opt = document.createElement('option');
    opt.value = '5';
    select.appendChild(opt);
    select.value = '5';
    select.dispatchEvent(new Event('change', { bubbles: true }));

    await vi.waitFor(() => expect(document.querySelector('.report-item')).not.toBeNull());
    const statValues = [...document.querySelectorAll('.stat-item span:last-child')].map(
      (el) => el.textContent
    );
    expect(statValues.every((v) => v === '0')).toBe(true);
  });

  // ── mount (lines 9-12) ────────────────────────────────────────────────────

  it('mount loads the template and returns a page with loadReportsProjects', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const page = await mount(container, { store: makeStore() });
    expect(typeof page.loadReportsProjects).toBe('function');
    container.remove();
  });
});
