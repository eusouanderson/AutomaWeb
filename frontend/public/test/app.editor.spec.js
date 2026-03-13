/**
 * Covers app.js lines 27-28: the `if (editorRoot)` true branch.
 * Needs a fresh module import with the `editor-tab` element present in the DOM.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('app.js – editor page mount when editor-tab is present', () => {
  let mountEditorPage;

  beforeEach(async () => {
    vi.resetModules();

    // Minimal DOM with the editor-tab element
    document.body.innerHTML = '<div id="editor-tab"></div>';

    // Stub all page modules
    vi.doMock('../state/store.js', () => ({ store: {} }));
    vi.doMock('../components/toast.js', () => ({ toast: vi.fn() }));
    vi.doMock('../router.js', () => ({
      initRouter: vi.fn(),
      navigateToTab: vi.fn()
    }));
    vi.doMock('../pages/dashboard/dashboard.page.js', () => ({
      mount: vi.fn().mockResolvedValue({ loadProjects: vi.fn().mockResolvedValue(undefined) })
    }));
    vi.doMock('../pages/generator/generator.page.js', () => ({
      mount: vi.fn().mockResolvedValue({
        loadProjectsDropdown: vi.fn().mockResolvedValue(undefined),
        generateFromExecutionFeedback: vi.fn().mockResolvedValue(undefined)
      })
    }));
    vi.doMock('../pages/scanner/scanner.page.js', () => ({
      mount: vi.fn().mockResolvedValue({
        loadTestsProjects: vi.fn().mockResolvedValue(undefined),
        loadExecuteProjects: vi.fn().mockResolvedValue(undefined)
      })
    }));
    vi.doMock('../pages/reports/reports.page.js', () => ({
      mount: vi
        .fn()
        .mockResolvedValue({ loadReportsProjects: vi.fn().mockResolvedValue(undefined) })
    }));

    mountEditorPage = vi.fn().mockResolvedValue(undefined);
    vi.doMock('../pages/robot-editor/editor.page.js', () => ({
      mount: mountEditorPage
    }));

    // Import app.js fresh so the editor-tab DOM element is found
    await import('../app.js');
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.resetModules();
  });

  it('calls mountEditorPage with the editor-tab element when it exists', () => {
    expect(mountEditorPage).toHaveBeenCalledTimes(1);
    const [el, ctx] = mountEditorPage.mock.calls[0];
    expect(el).toBeInstanceOf(HTMLElement);
    expect(el.id).toBe('editor-tab');
    expect(ctx).toHaveProperty('store');
  });
});
