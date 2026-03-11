import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  getProjectExecutions: vi.fn()
}));
vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));
vi.mock('../../../utils/helpers.js', () => ({
  escapeHtml: (v) => String(v ?? ''),
  formatDate: (v) => (v ? String(v) : '-')
}));

import { toast } from '../../../components/toast.js';
import { getProjectExecutions, getProjects } from '../../../services/test.service.js';
import { initReportsPage } from '../reports.page.js';

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
    }
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
        created_at: '2024'
      }
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
        created_at: '2024'
      }
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
        log_file: null
      }
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
});
