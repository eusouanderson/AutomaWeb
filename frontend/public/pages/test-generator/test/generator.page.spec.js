import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ── mock external dependencies ──────────────────────────────────────────────

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
  generateTestFromPrompt: vi.fn()
}));

vi.mock('../../../utils/dom.js', async () => {
  const actual = await vi.importActual('../../../utils/dom.js');
  return {
    ...actual,
    // loadTemplate resolves immediately with inline HTML (no fetch needed)
    loadTemplate: vi.fn().mockResolvedValue(`
      <section>
        <form id="generator-form">
          <select id="generator-project" required></select>
          <textarea id="generator-prompt" rows="5" required></textarea>
          <textarea id="generator-context" rows="4"></textarea>
          <div id="generator-actions"></div>
        </form>
        <div id="generation-progress" class="hidden"></div>
        <div id="generated-output" class="hidden">
          <div id="generated-output-actions"></div>
          <pre><code id="generated-code"></code></pre>
        </div>
      </section>
    `)
  };
});

vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));

// ── imports (after mocks) ────────────────────────────────────────────────────
import { toast } from '../../../components/toast.js';
import { generateTestFromPrompt, getProjects } from '../../../services/test.service.js';
import { createLoader, mount } from '../generator.page.js';

// ── helpers ──────────────────────────────────────────────────────────────────
function makeContext(projects = []) {
  let state = { projects, lastGeneratedTest: null };
  return {
    store: {
      getState: () => state,
      setState: (partial) => {
        state = { ...state, ...partial };
      }
    }
  };
}

function makeRoot() {
  const root = document.createElement('div');
  document.body.appendChild(root);
  return root;
}

// ── tests ────────────────────────────────────────────────────────────────────
describe('test-generator page – mount', () => {
  let root;

  beforeEach(() => {
    localStorage.clear();
    root = makeRoot();
    vi.clearAllMocks();
  });

  afterEach(() => {
    root.remove();
  });

  it('renders the form after mount', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());
    expect(root.querySelector('#generator-form')).not.toBeNull();
  });

  it('populates select with projects from store', async () => {
    const context = makeContext([{ id: 1, name: 'Proj A' }]);
    await mount(root, context);
    const options = root.querySelectorAll('#generator-project option');
    // placeholder + 1 project
    expect(options.length).toBe(2);
    expect(options[1].textContent).toBe('Proj A');
  });

  it('fetches projects from API when store has none', async () => {
    getProjects.mockResolvedValue([{ id: 2, name: 'Proj B' }]);
    await mount(root, makeContext([]));
    const options = root.querySelectorAll('#generator-project option');
    expect(options.length).toBe(2);
    expect(options[1].textContent).toBe('Proj B');
  });

  it('restores prompt and context from localStorage', async () => {
    localStorage.setItem('generator_prompt', 'my saved prompt');
    localStorage.setItem('generator_context', 'my saved context');
    getProjects.mockResolvedValue([]);

    await mount(root, makeContext());
    expect(root.querySelector('#generator-prompt').value).toBe('my saved prompt');
    expect(root.querySelector('#generator-context').value).toBe('my saved context');
  });

  it('saves prompt to localStorage on input', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());

    const prompt = root.querySelector('#generator-prompt');
    prompt.value = 'typed prompt';
    prompt.dispatchEvent(new Event('input'));

    expect(localStorage.getItem('generator_prompt')).toBe('typed prompt');
  });

  it('saves context to localStorage on input', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());

    const ctx = root.querySelector('#generator-context');
    ctx.value = 'typed context';
    ctx.dispatchEvent(new Event('input'));

    expect(localStorage.getItem('generator_context')).toBe('typed context');
  });

  it('calls generateTestFromPrompt on form submit', async () => {
    const context = makeContext([{ id: 1, name: 'Proj A' }]);
    generateTestFromPrompt.mockResolvedValue({ id: 10, content: '*** Test Cases ***' });
    await mount(root, context);

    root.querySelector('#generator-project').value = '1';
    root.querySelector('#generator-prompt').value = 'Login test';

    const form = root.querySelector('#generator-form');
    form.dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(generateTestFromPrompt).toHaveBeenCalledTimes(1));
    const call = generateTestFromPrompt.mock.calls[0][0];
    expect(call.projectId).toBe(1);
    expect(call.prompt).toBe('Login test');
  });

  it('shows generated output after successful generation', async () => {
    const context = makeContext([{ id: 1, name: 'Proj A' }]);
    generateTestFromPrompt.mockResolvedValue({ id: 11, content: '*** Settings ***' });
    await mount(root, context);

    root.querySelector('#generator-project').value = '1';
    root.querySelector('#generator-prompt').value = 'My prompt';

    root.querySelector('#generator-form').dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() =>
      expect(root.querySelector('#generated-output').classList.contains('hidden')).toBe(false)
    );

    expect(root.querySelector('#generated-code').textContent).toBe('*** Settings ***');
  });

  it('shows an error toast when generation fails', async () => {
    const context = makeContext([{ id: 1, name: 'Proj' }]);
    generateTestFromPrompt.mockRejectedValue(new Error('Server error'));
    await mount(root, context);

    root.querySelector('#generator-project').value = '1';
    root.querySelector('#generator-prompt').value = 'fail';
    root.querySelector('#generator-form').dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Server error', 'error'));
  });

  it('returns an unmount cleanup function', async () => {
    getProjects.mockResolvedValue([]);
    const cleanup = await mount(root, makeContext());
    expect(typeof cleanup).toBe('function');
  });

  it('calling the cleanup function removes the submit listener and modal', async () => {
    getProjects.mockResolvedValue([]);
    const cleanup = await mount(root, makeContext());
    const form = root.querySelector('#generator-form');
    const spy = vi.spyOn(form, 'removeEventListener');
    cleanup();
    expect(spy).toHaveBeenCalledWith('submit', expect.any(Function));
  });

  it('copy code button writes to clipboard and shows toast', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    const context = makeContext([{ id: 1, name: 'Proj A' }]);
    generateTestFromPrompt.mockResolvedValue({ id: 1, content: '*** Test Cases ***' });
    await mount(root, context);

    // Trigger generation so codeBlock has content
    root.querySelector('#generator-project').value = '1';
    root.querySelector('#generator-prompt').value = 'test copy';
    root.querySelector('#generator-form').dispatchEvent(new Event('submit', { bubbles: true }));
    await vi.waitFor(() => expect(generateTestFromPrompt).toHaveBeenCalled());
    await vi.waitFor(() =>
      expect(root.querySelector('#generated-code').textContent).toBe('*** Test Cases ***')
    );

    // Click the Copy code button
    const copyBtn = Array.from(root.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Copy code')
    );
    copyBtn.click();
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith('*** Test Cases ***'));
    expect(toast).toHaveBeenCalledWith('Code copied');

    vi.unstubAllGlobals();
  });

  it('copy code uses empty string when code block has no content', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());

    // click Copy without running generation — codeBlock is empty
    const copyBtn = Array.from(root.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Copy code')
    );
    copyBtn.click();
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith(''));

    vi.unstubAllGlobals();
  });

  it('activates the generate step after 2500ms when API is slow', async () => {
    vi.useFakeTimers();
    try {
      const context = makeContext([{ id: 1, name: 'Proj' }]);
      getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
      let resolveApi;
      generateTestFromPrompt.mockReturnValue(
        new Promise((res) => {
          resolveApi = res;
        })
      );

      await mount(root, context);

      root.querySelector('#generator-project').value = '1';
      root.querySelector('#generator-prompt').value = 'slow test';
      root.querySelector('#generator-form').dispatchEvent(new Event('submit', { bubbles: true }));

      await vi.advanceTimersByTimeAsync(2600);

      const generateStep = root.querySelector('[data-step="generate"]');
      expect(generateStep?.className).toContain('gen-step--active');

      // resolve the API to let the async handler finish cleanly
      resolveApi({ id: 1, content: '' });
      await vi.runAllTimersAsync();
    } finally {
      vi.useRealTimers();
    }
  });

  // ── buildProgressTracker.activate: !el continue branch (line 38) ─────────

  it('buildProgressTracker activate skips null step element via continue', async () => {
    vi.useFakeTimers();
    try {
      const context = makeContext([{ id: 1, name: 'Proj' }]);
      getProjects.mockResolvedValue([{ id: 1, name: 'Proj' }]);
      let resolveApi;
      generateTestFromPrompt.mockReturnValue(
        new Promise((res) => {
          resolveApi = res;
        })
      );

      await mount(root, context);

      root.querySelector('#generator-project').value = '1';
      root.querySelector('#generator-prompt').value = 'step removal test';
      root.querySelector('#generator-form').dispatchEvent(new Event('submit', { bubbles: true }));

      // Synchronous submit init is complete; buildProgressTracker has set progressEl innerHTML.
      // Remove the 'analyze' step element so getEl('analyze') returns null on the next activate().
      root.querySelector('[data-step="analyze"]')?.remove();

      // Advance past step2Timer (2500ms) → tracker.activate('generate');
      // for-loop iterates: getEl('analyze') = null → continue  ← covers line 38
      await vi.advanceTimersByTimeAsync(2600);
      expect(root.querySelector('[data-step="generate"]')?.className).toContain('gen-step--active');

      resolveApi({ id: 1, content: '' });
      await vi.runAllTimersAsync();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('createLoader', () => {
  it('returns a div with loader class', () => {
    const el = createLoader('Please wait');
    expect(el.tagName).toBe('DIV');
    expect(el.className).toBe('loader');
  });

  it('renders the provided label text', () => {
    const el = createLoader('Please wait');
    expect(el.textContent).toContain('Please wait');
  });

  it('uses default label when none is provided', () => {
    const el = createLoader();
    expect(el.textContent).toContain('Loading...');
  });

  it('contains a .loader-dot span', () => {
    const el = createLoader();
    expect(el.querySelector('.loader-dot')).not.toBeNull();
  });
});
