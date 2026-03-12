import { describe, expect, it, vi } from 'vitest';

vi.mock('../state/store.js', () => ({ store: {} }));
vi.mock('../components/toast.js', () => ({ toast: vi.fn() }));

vi.mock('../router.js', () => ({
  initRouter: vi.fn(),
  navigateToTab: vi.fn()
}));

vi.mock('../pages/dashboard/dashboard.page.js', () => ({
  initDashboardPage: vi.fn(() => ({
    loadProjects: vi.fn().mockResolvedValue(undefined)
  }))
}));

vi.mock('../pages/generator/generator.page.js', () => ({
  initGeneratorPage: vi.fn(() => ({
    loadProjectsDropdown: vi.fn().mockResolvedValue(undefined),
    generateFromExecutionFeedback: vi.fn().mockResolvedValue(undefined)
  }))
}));

vi.mock('../pages/scanner/scanner.page.js', () => ({
  initScannerPage: vi.fn(() => ({
    loadTestsProjects: vi.fn().mockResolvedValue(undefined),
    loadExecuteProjects: vi.fn().mockResolvedValue(undefined)
  }))
}));

vi.mock('../pages/reports/reports.page.js', () => ({
  initReportsPage: vi.fn(() => ({
    loadReportsProjects: vi.fn().mockResolvedValue(undefined)
  }))
}));

vi.mock('../pages/robot-editor/editor.page.js', () => ({
  mount: vi.fn().mockResolvedValue(undefined)
}));

import { toast } from '../components/toast.js';
import { initDashboardPage } from '../pages/dashboard/dashboard.page.js';
import { initGeneratorPage } from '../pages/generator/generator.page.js';
import { initReportsPage } from '../pages/reports/reports.page.js';
import { initScannerPage } from '../pages/scanner/scanner.page.js';
import { initRouter } from '../router.js';

// Load the app entry point — all side-effects run with mocked dependencies
await import('../app.js');

describe('app.js bootstrap', () => {
  it('initializes all four page modules', () => {
    expect(initDashboardPage).toHaveBeenCalledTimes(1);
    expect(initGeneratorPage).toHaveBeenCalledTimes(1);
    expect(initReportsPage).toHaveBeenCalledTimes(1);
    expect(initScannerPage).toHaveBeenCalledTimes(1);
  });

  it('calls loadProjects on dashboard at startup', () => {
    const page = initDashboardPage.mock.results[0].value;
    expect(page.loadProjects).toHaveBeenCalledTimes(1);
  });

  it('calls loadProjectsDropdown on generator at startup', () => {
    const page = initGeneratorPage.mock.results[0].value;
    expect(page.loadProjectsDropdown).toHaveBeenCalledTimes(1);
  });

  it('calls loadExecuteProjects on scanner at startup', () => {
    const page = initScannerPage.mock.results[0].value;
    expect(page.loadExecuteProjects).toHaveBeenCalledTimes(1);
  });

  it('calls loadReportsProjects on reports at startup', () => {
    const page = initReportsPage.mock.results[0].value;
    expect(page.loadReportsProjects).toHaveBeenCalledTimes(1);
  });

  it('passes store to dashboard, generator, and reports', () => {
    expect(initDashboardPage.mock.calls[0][0]).toHaveProperty('store');
    expect(initGeneratorPage.mock.calls[0][0]).toHaveProperty('store');
    expect(initReportsPage.mock.calls[0][0]).toHaveProperty('store');
  });

  it('passes store and onRecreateRequested to scanner', () => {
    const call = initScannerPage.mock.calls[0][0];
    expect(call).toHaveProperty('store');
    expect(typeof call.onRecreateRequested).toBe('function');
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
    const page = initScannerPage.mock.results[0].value;
    const callsBefore = page.loadTestsProjects.mock.calls.length;
    await onTabChange('tests');
    expect(page.loadTestsProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers scanner.loadExecuteProjects for "execute" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = initScannerPage.mock.results[0].value;
    const callsBefore = page.loadExecuteProjects.mock.calls.length;
    await onTabChange('execute');
    expect(page.loadExecuteProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers generator.loadProjectsDropdown for "generate" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = initGeneratorPage.mock.results[0].value;
    const callsBefore = page.loadProjectsDropdown.mock.calls.length;
    await onTabChange('generate');
    expect(page.loadProjectsDropdown.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers reports.loadReportsProjects for "reports" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = initReportsPage.mock.results[0].value;
    const callsBefore = page.loadReportsProjects.mock.calls.length;
    await onTabChange('reports');
    expect(page.loadReportsProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers dashboard.loadProjects for "projects" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = initDashboardPage.mock.results[0].value;
    const callsBefore = page.loadProjects.mock.calls.length;
    await onTabChange('projects');
    expect(page.loadProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers generator.loadProjectsDropdown for "generate" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = initGeneratorPage.mock.results[0].value;
    const callsBefore = page.loadProjectsDropdown.mock.calls.length;
    await onTabChange('generate');
    expect(page.loadProjectsDropdown.mock.calls.length).toBe(callsBefore + 1);
  });

  it('router onTabChange triggers reports.loadReportsProjects for "reports" tab', async () => {
    const { onTabChange } = initRouter.mock.calls[0][0];
    const page = initReportsPage.mock.results[0].value;
    const callsBefore = page.loadReportsProjects.mock.calls.length;
    await onTabChange('reports');
    expect(page.loadReportsProjects.mock.calls.length).toBe(callsBefore + 1);
  });

  it('onRecreateRequested calls generateFromExecutionFeedback and navigateToTab', async () => {
    const { navigateToTab } = await import('../router.js');
    const { onRecreateRequested } = initScannerPage.mock.calls[0][0];
    const genPage = initGeneratorPage.mock.results[0].value;

    await onRecreateRequested({ projectId: 2, feedback: 'fix this' });

    expect(genPage.generateFromExecutionFeedback).toHaveBeenCalledWith(2, 'fix this');
    expect(navigateToTab).toHaveBeenCalledWith('generate');
  });
});
