import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initRouter, navigateToTab } from '../router.js';

function buildTabDOM() {
  document.body.innerHTML = `
    <button class="tab-btn" data-tab="projects">Projects</button>
    <button class="tab-btn" data-tab="generate">Generate</button>
    <button class="tab-btn" data-tab="tests">Tests</button>
    <button class="tab-btn" data-tab="execute">Execute</button>
    <button class="tab-btn" data-tab="reports">Reports</button>
    <div class="tab-content" id="projects-tab"></div>
    <div class="tab-content" id="generate-tab"></div>
    <div class="tab-content" id="tests-tab"></div>
    <div class="tab-content" id="execute-tab"></div>
    <div class="tab-content" id="reports-tab"></div>
  `;
}

describe('router', () => {
  beforeEach(() => {
    buildTabDOM();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  // ── navigateToTab ─────────────────────────────────────────────────────────

  describe('navigateToTab', () => {
    it('sets location.hash for a valid tab', () => {
      navigateToTab('generate');
      expect(globalThis.location.hash).toBe('#generate');
    });

    it('ignores unknown tab names without changing hash', () => {
      navigateToTab('projects');
      navigateToTab('unknown-tab');
      expect(globalThis.location.hash).toBe('#projects');
    });

    it('accepts all five valid tabs', () => {
      for (const tab of ['projects', 'generate', 'tests', 'execute', 'reports']) {
        navigateToTab(tab);
        expect(globalThis.location.hash).toBe(`#${tab}`);
      }
    });
  });

  // ── initRouter ────────────────────────────────────────────────────────────

  describe('initRouter', () => {
    it('calls onTabChange on init with the current hash tab', async () => {
      globalThis.location.hash = '#generate';
      const onTabChange = vi.fn().mockResolvedValue(undefined);
      initRouter({ onTabChange });
      await vi.waitFor(() => expect(onTabChange).toHaveBeenCalledWith('generate'));
    });

    it('defaults to "projects" when hash is not a known tab', async () => {
      globalThis.location.hash = '#invalid';
      const onTabChange = vi.fn().mockResolvedValue(undefined);
      initRouter({ onTabChange });
      await vi.waitFor(() => expect(onTabChange).toHaveBeenCalledWith('projects'));
    });

    it('marks the current tab button as active', async () => {
      globalThis.location.hash = '#generate';
      initRouter({ onTabChange: vi.fn().mockResolvedValue(undefined) });
      await vi.waitFor(() => {
        expect(document.querySelector('[data-tab="generate"]')?.classList.contains('active')).toBe(
          true
        );
      });
    });

    it('removes active class from other tab buttons', async () => {
      globalThis.location.hash = '#generate';
      initRouter({ onTabChange: vi.fn().mockResolvedValue(undefined) });
      await vi.waitFor(() => {
        expect(document.querySelector('[data-tab="projects"]')?.classList.contains('active')).toBe(
          false
        );
      });
    });

    it('shows the active tab content element', async () => {
      globalThis.location.hash = '#tests';
      initRouter({ onTabChange: vi.fn().mockResolvedValue(undefined) });
      await vi.waitFor(() => {
        expect(document.getElementById('tests-tab')?.classList.contains('active')).toBe(true);
      });
    });

    it('hides other tab content elements', async () => {
      globalThis.location.hash = '#tests';
      initRouter({ onTabChange: vi.fn().mockResolvedValue(undefined) });
      await vi.waitFor(() => {
        expect(document.getElementById('projects-tab')?.classList.contains('active')).toBe(false);
      });
    });

    it('clicking a tab button navigates to that tab', () => {
      initRouter({ onTabChange: vi.fn().mockResolvedValue(undefined) });
      document.querySelector('[data-tab="execute"]')?.click();
      expect(globalThis.location.hash).toBe('#execute');
    });

    it('sets hash to "projects" when location.hash is empty on init', async () => {
      globalThis.location.hash = '';
      const onTabChange = vi.fn().mockResolvedValue(undefined);
      initRouter({ onTabChange });
      await vi.waitFor(() => expect(globalThis.location.hash).toBe('#projects'));
    });

    it('fires onTabChange again when hashchange event is dispatched', async () => {
      globalThis.location.hash = '#projects';
      const onTabChange = vi.fn().mockResolvedValue(undefined);
      initRouter({ onTabChange });

      await vi.waitFor(() => expect(onTabChange).toHaveBeenCalledTimes(1));

      globalThis.location.hash = '#reports';
      globalThis.dispatchEvent(new Event('hashchange'));

      await vi.waitFor(() => expect(onTabChange).toHaveBeenCalledTimes(2));
      expect(onTabChange).toHaveBeenLastCalledWith('reports');
    });

    it('getTabFromHash falls back to "projects" when hash is empty during hashchange', async () => {
      // init with a valid hash so the initRouter guard does not fire
      globalThis.location.hash = '#generate';
      const onTabChange = vi.fn().mockResolvedValue(undefined);
      initRouter({ onTabChange });
      await vi.waitFor(() => expect(onTabChange).toHaveBeenCalledWith('generate'));
      onTabChange.mockClear();

      // Set hash to empty so getTabFromHash sees '' and exercises the || branch
      globalThis.location.hash = '';
      globalThis.dispatchEvent(new Event('hashchange'));

      await vi.waitFor(() => expect(onTabChange).toHaveBeenCalledWith('projects'));
    });
  });
});
