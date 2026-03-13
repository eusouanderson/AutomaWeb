import { describe, expect, it, vi } from 'vitest';

vi.mock('../state/store.js', () => ({ store: {} }));
vi.mock('../components/toast.js', () => ({ toast: vi.fn() }));

vi.mock('../router.js', () => ({
  initRouter: vi.fn(),
  navigateToTab: vi.fn()
}));

vi.mock('../pages/dashboard/dashboard.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadProjects: vi.fn().mockResolvedValue(undefined)
  })
}));

vi.mock('../pages/generator/generator.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadProjectsDropdown: vi.fn().mockResolvedValue(undefined),
    generateFromExecutionFeedback: vi.fn().mockResolvedValue(undefined)
  })
}));

vi.mock('../pages/scanner/scanner.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadTestsProjects: vi.fn().mockResolvedValue(undefined),
    loadExecuteProjects: vi.fn().mockResolvedValue(undefined)
  })
}));

vi.mock('../pages/reports/reports.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadReportsProjects: vi.fn().mockResolvedValue(undefined)
  })
}));

vi.mock('../pages/robot-editor/editor.page.js', () => ({
  mount: vi.fn().mockResolvedValue(undefined)
}));

import { toast } from '../components/toast.js';
import { mount as mountDashboardPage } from '../pages/dashboard/dashboard.page.js';
import { mount as mountGeneratorPage } from '../pages/generator/generator.page.js';
import { mount as mountReportsPage } from '../pages/reports/reports.page.js';
import { mount as mountScannerPage } from '../pages/scanner/scanner.page.js';
import { initRouter } from '../router.js';

// Provide the DOM structure that app.js needs before importing it
document.body.innerHTML = `
  <div id="projects-tab" class="tab-content active"></div>
  <div id="generate-tab" class="tab-content"></div>
  <div id="tests-tab" class="tab-content"></div>
  <div id="execute-tab" class="tab-content"></div>
  <div id="editor-tab" class="tab-content"></div>
  <div id="reports-tab" class="tab-content"></div>
`;

// Load the app entry point — all side-effects run with mocked dependencies
await import('../app.js');

describe('app.js bootstrap', () => {
  it('mounts all four page modules', () => {
    expect(mountDashboardPage).toHaveBeenCalledTimes(1);
    expect(mountGeneratorPage).toHaveBeenCalledTimes(1);
    expect(mountReportsPage).toHaveBeenCalledTimes(1);
    expect(mountScannerPage).toHaveBeenCalledTimes(1);
  });

  it('calls loadProjects on dashboard at startup', async () => {
    const page = await mountDashboardPage.mock.results[0].value;
    expect(page.loadProjects).toHaveBeenCalledTimes(1);
  });

  it('calls loadProjectsDropdown on generator at startup', async () => {
    const page = await mountGeneratorPage.mock.results[0].value;
    expect(page.loadProjectsDropdown).toHaveBeenCalledTimes(1);
  });

  it('calls loadExecuteProjects on scanner at startup', async () => {
    const page = await mountScannerPage.mock.results[0].value;
    expect(page.loadExecuteProjects).toHaveBeenCalledTimes(1);
  });

  it('calls loadReportsProjects on reports at startup', async () => {
    const page = await mountReportsPage.mock.results[0].value;
    expect(page.loadReportsProjects).toHaveBeenCalledTimes(1);
  });

  it('passes store to dashboard, generator, and reports', () => {
    expect(mountDashboardPage.mock.calls[0][1]).toHaveProperty('store');
    expect(mountGeneratorPage.mock.calls[0][1]).toHaveProperty('store');
    expect(mountReportsPage.mock.calls[0][1]).toHaveProperty('store');
  });

  it('passes store and onRecreateRequested to scanner', () => {
    const opts = mountScannerPage.mock.calls[0][1];
    expect(opts).toHaveProperty('store');
    expect(typeof opts.onRecreateRequested).toBe('function');
  });

  it('passes root elements to page mounts', () => {
    expect(mountDashboardPage.mock.calls[0][0]).toBeInstanceOf(HTMLElement);
    expect(mountGeneratorPage.mock.calls[0][0]).toBeInstanceOf(HTMLElement);
    expect(mountReportsPage.mock.calls[0][0]).toBeInstanceOf(HTMLElement);
    const roots = mountScannerPage.mock.calls[0][0];
    expect(roots).toHaveProperty('testsRoot');
    expect(roots).toHaveProperty('executeRoot');
  });

  it('sets up the router', () => {
    expect(initRouter).toHaveBeenCalledTimes(1);
    const routerCall = initRouter.mock.calls[0][0];
    expect(typeof routerCall.onTabChange).toBe('function');
  });

  it('shows an info toast after loading', () => {
    expect(toast).toHaveBeenCalledWith('Frontend carregado', 'info');
  });

  it('router onTabChange triggers scanner.loadTestsProjects for "tests" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = await mountScannerPage.mock.results[0].value;
    const callsBefore = page.loadTestsProjects.mock.calls.length;
    await onTabChange('tests');
    expect(page.loadTestsProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers scanner.loadExecuteProjects for "execute" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = await mountScannerPage.mock.results[0].value;
    const callsBefore = page.loadExecuteProjects.mock.calls.length;
    await onTabChange('execute');
    expect(page.loadExecuteProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers generator.loadProjectsDropdown for "generate" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = await mountGeneratorPage.mock.results[0].value;
    const callsBefore = page.loadProjectsDropdown.mock.calls.length;
    await onTabChange('generate');
    expect(page.loadProjectsDropdown.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers reports.loadReportsProjects for "reports" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = await mountReportsPage.mock.results[0].value;
    const callsBefore = page.loadReportsProjects.mock.calls.length;
    await onTabChange('reports');
    expect(page.loadReportsProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers dashboard.loadProjects for "projects" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = await mountDashboardPage.mock.results[0].value;
    const callsBefore = page.loadProjects.mock.calls.length;
    await onTabChange('projects');
    expect(page.loadProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers reports.loadReportsProjects for "reports" tab (alias)', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = await mountReportsPage.mock.results[0].value;
    const callsBefore = page.loadReportsProjects.mock.calls.length;
    await onTabChange('reports');
    expect(page.loadReportsProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('onRecreateRequested calls generateFromExecutionFeedback and navigateToTab', async () => {
    const { navigateToTab } = await import('../router.js');
    const opts = mountScannerPage.mock.calls[0][1];
    const { onRecreateRequested } = opts;
    const genPage = await mountGeneratorPage.mock.results[0].value;

    await onRecreateRequested({ projectId: 2, feedback: 'fix this', testIds: [1] });

    expect(genPage.generateFromExecutionFeedback).toHaveBeenCalledWith(2, 'fix this', [1]);
    expect(navigateToTab).toHaveBeenCalledWith('generate');
  });
});

