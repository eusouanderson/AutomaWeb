import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  createProjectService: vi.fn(),
  deleteProjectService: vi.fn()
}));
vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));
vi.mock('../../../utils/helpers.js', () => ({
  escapeHtml: (v) => String(v ?? ''),
  formatDate: (v) => (v ? String(v) : '-')
}));

vi.mock('../../../utils/dom.js', async () => {
  const actual = await vi.importActual('../../../utils/dom.js');
  return { ...actual, loadTemplate: vi.fn().mockResolvedValue('') };
});

import { toast } from '../../../components/toast.js';
import {
  createProjectService,
  deleteProjectService,
  getProjects
} from '../../../services/test.service.js';
import { initDashboardPage, mount } from '../dashboard.page.js';

function buildDOM() {
  document.body.innerHTML = `
    <form id="create-project-form">
      <input id="project-name" value="" />
      <input id="project-description" value="" />
      <input id="project-url" value="" />
      <input id="project-test-dir" value="" />
      <button type="submit">Create</button>
    </form>
    <div id="projects-list"></div>
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

describe('dashboard.page – initDashboardPage', () => {
  beforeEach(() => {
    buildDOM();
    vi.clearAllMocks();
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  // ── early return without DOM ────────────────────────────────────────────────

  it('returns a no-op loadProjects when DOM elements are missing', async () => {
    document.body.innerHTML = '';
    const page = initDashboardPage({ store: makeStore() });
    await expect(page.loadProjects()).resolves.toBeUndefined();
  });

  // ── loadProjects ──────────────────────────────────────────────────────────

  it('renders a project card for each project', async () => {
    getProjects.mockResolvedValue([
      { id: 1, name: 'Alpha', description: 'desc', url: 'https://a.com', created_at: '2024' }
    ]);
    const page = initDashboardPage({ store: makeStore() });
    await page.loadProjects();
    expect(document.getElementById('projects-list').textContent).toContain('Alpha');
  });

  it('stores projects on the store after loading', async () => {
    const projects = [{ id: 2, name: 'Beta', created_at: null }];
    getProjects.mockResolvedValue(projects);
    const store = makeStore();
    const page = initDashboardPage({ store });
    await page.loadProjects();
    expect(store.getState().projects).toEqual(projects);
  });

  it('shows empty state when no projects exist', async () => {
    getProjects.mockResolvedValue([]);
    const page = initDashboardPage({ store: makeStore() });
    await page.loadProjects();
    expect(document.getElementById('projects-list').textContent).toContain('Nenhum projeto');
  });

  it('shows error state and toasts on load failure', async () => {
    getProjects.mockRejectedValue(new Error('Network fail'));
    const page = initDashboardPage({ store: makeStore() });
    await page.loadProjects();
    expect(document.getElementById('projects-list').textContent).toContain('Erro');
    expect(toast).toHaveBeenCalledWith('Network fail', 'error');
  });

  // ── create project form ───────────────────────────────────────────────────

  it('calls createProjectService on form submit', async () => {
    getProjects.mockResolvedValue([]);
    createProjectService.mockResolvedValue({ id: 10 });
    initDashboardPage({ store: makeStore() });

    document.getElementById('project-name').value = 'My Project';
    document
      .getElementById('create-project-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(createProjectService).toHaveBeenCalledTimes(1));
    expect(createProjectService).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'My Project' })
    );
  });

  it('shows success toast after project creation', async () => {
    getProjects.mockResolvedValue([]);
    createProjectService.mockResolvedValue({ id: 11 });
    initDashboardPage({ store: makeStore() });

    document
      .getElementById('create-project-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Projeto criado com sucesso!'));
  });

  it('shows error toast when creation fails', async () => {
    createProjectService.mockRejectedValue(new Error('Conflict'));
    initDashboardPage({ store: makeStore() });

    document
      .getElementById('create-project-form')
      .dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Conflict', 'error'));
  });

  // ── delete project ────────────────────────────────────────────────────────

  it('calls deleteProjectService when delete button is clicked and confirmed', async () => {
    getProjects.mockResolvedValue([{ id: 5, name: 'ToDelete', created_at: null }]);
    deleteProjectService.mockResolvedValue(undefined);
    getProjects
      .mockResolvedValueOnce([{ id: 5, name: 'ToDelete', created_at: null }])
      .mockResolvedValueOnce([]);

    const page = initDashboardPage({ store: makeStore() });
    await page.loadProjects();

    document.querySelector('[data-project-id="5"]')?.click();
    await vi.waitFor(() => expect(deleteProjectService).toHaveBeenCalledWith(5));
  });

  it('shows success toast after deletion', async () => {
    getProjects
      .mockResolvedValueOnce([{ id: 5, name: 'X', created_at: null }])
      .mockResolvedValueOnce([]);
    deleteProjectService.mockResolvedValue(undefined);
    const page = initDashboardPage({ store: makeStore() });
    await page.loadProjects();

    document.querySelector('[data-project-id="5"]')?.click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Projeto deletado com sucesso!'));
  });

  it('does not delete when user cancels confirm', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false));
    getProjects.mockResolvedValue([{ id: 5, name: 'X', created_at: null }]);
    const page = initDashboardPage({ store: makeStore() });
    await page.loadProjects();

    document.querySelector('[data-project-id="5"]')?.click();
    await new Promise((r) => setTimeout(r, 50));
    expect(deleteProjectService).not.toHaveBeenCalled();
  });

  it('shows error toast when deletion fails', async () => {
    getProjects.mockResolvedValue([{ id: 5, name: 'X', created_at: null }]);
    deleteProjectService.mockRejectedValue(new Error('Server error'));
    const page = initDashboardPage({ store: makeStore() });
    await page.loadProjects();

    document.querySelector('[data-project-id="5"]')?.click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Server error', 'error'));
  });

  // ── list click: no [data-project-id] target (lines 74-75) ────────────────

  it('does nothing when clicking list content with no delete button ancestor', () => {
    initDashboardPage({ store: makeStore() });
    document.getElementById('projects-list').innerHTML =
      '<div class="plain"><span>some text</span></div>';
    document
      .querySelector('#projects-list .plain span')
      .dispatchEvent(new Event('click', { bubbles: true }));
    expect(deleteProjectService).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalled();
  });

  // ── list click: falsy projectId (lines 79-80) ─────────────────────────────

  it('does nothing when delete button has empty data-project-id', () => {
    initDashboardPage({ store: makeStore() });
    document.getElementById('projects-list').innerHTML =
      '<button data-project-id="">Delete</button>';
    document.querySelector('[data-project-id]').click();
    expect(deleteProjectService).not.toHaveBeenCalled();
  });

  // ── mount (lines 13-16) ───────────────────────────────────────────────────

  it('mount loads the template and returns a page with loadProjects', async () => {
    const root = document.createElement('div');
    document.body.appendChild(root);
    const page = await mount(root, { store: makeStore() });
    expect(typeof page.loadProjects).toBe('function');
    root.remove();
  });
});
