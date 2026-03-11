import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ── mocks ────────────────────────────────────────────────────────────────────
vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn()
}));

vi.mock('../../../services/scan.service.js', () => ({
  runProjectScan: vi.fn()
}));

vi.mock('../../../utils/dom.js', async () => {
  const actual = await vi.importActual('../../../utils/dom.js');
  return {
    ...actual,
    loadTemplate: vi.fn().mockResolvedValue(`
      <section>
        <form id="scan-form">
          <select id="scan-project" required>
            <option value="">Select project</option>
          </select>
          <div id="scan-action-slot"></div>
        </form>
        <div id="scan-progress"></div>
        <div id="scan-summary">No scan yet.</div>
      </section>
    `)
  };
});

vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));

// ── imports ───────────────────────────────────────────────────────────────────
import { toast } from '../../../components/toast.js';
import { runProjectScan } from '../../../services/scan.service.js';
import { getProjects } from '../../../services/test.service.js';
import { mount } from '../scan.page.js';

// ── helpers ───────────────────────────────────────────────────────────────────
function makeContext(projects = []) {
  let state = { projects, lastScanResult: null };
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

// ── tests ─────────────────────────────────────────────────────────────────────
describe('project-scan page – mount', () => {
  let root;

  beforeEach(() => {
    root = makeRoot();
    vi.clearAllMocks();
  });

  afterEach(() => {
    root.remove();
  });

  it('renders the scan form', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());
    expect(root.querySelector('#scan-form')).not.toBeNull();
  });

  it('renders a submit button in the action slot', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());
    const slot = root.querySelector('#scan-action-slot');
    expect(slot?.querySelector('button')).not.toBeNull();
  });

  it('populates select from store when projects are present', async () => {
    const context = makeContext([{ id: 1, name: 'Demo', url: 'https://demo.com' }]);
    await mount(root, context);
    const options = root.querySelectorAll('#scan-project option');
    expect(options.length).toBe(2);
    expect(options[1].textContent).toBe('Demo');
  });

  it('fetches projects from API when store is empty', async () => {
    getProjects.mockResolvedValue([{ id: 3, name: 'API Proj', url: 'https://api.com' }]);
    await mount(root, makeContext([]));
    expect(getProjects).toHaveBeenCalledTimes(1);
    const options = root.querySelectorAll('#scan-project option');
    expect(options.length).toBe(2);
  });

  it('calls runProjectScan on form submit', async () => {
    const context = makeContext([{ id: 1, name: 'Demo', url: 'https://demo.com' }]);
    runProjectScan.mockResolvedValue({
      title: 'Demo Page',
      total_elements: 5,
      summary: { input: 2, button: 3 }
    });

    await mount(root, context);
    const select = root.querySelector('#scan-project');
    select.value = '1';
    // mirror data-url on the selected option
    select.options[select.selectedIndex]?.setAttribute('data-url', 'https://demo.com');

    root.querySelector('#scan-form').dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(runProjectScan).toHaveBeenCalledTimes(1));
  });

  it('displays scan summary after a successful scan', async () => {
    const context = makeContext([{ id: 1, name: 'Demo', url: 'https://demo.com' }]);
    runProjectScan.mockResolvedValue({
      title: 'My Page',
      total_elements: 10,
      summary: { button: 10 }
    });

    await mount(root, context);
    const select = root.querySelector('#scan-project');
    select.value = '1';
    select.options[select.selectedIndex]?.setAttribute('data-url', 'https://demo.com');

    root.querySelector('#scan-form').dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Scan finished'));
    expect(root.querySelector('#scan-summary').textContent).toContain('My Page');
  });

  it('shows error toast when scan fails', async () => {
    const context = makeContext([{ id: 1, name: 'Demo', url: 'https://fail.com' }]);
    runProjectScan.mockRejectedValue(new Error('Network error'));

    await mount(root, context);
    const select = root.querySelector('#scan-project');
    select.value = '1';
    select.options[select.selectedIndex]?.setAttribute('data-url', 'https://fail.com');

    root.querySelector('#scan-form').dispatchEvent(new Event('submit', { bubbles: true }));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Network error', 'error'));
  });

  it('returns an unmount cleanup function', async () => {
    getProjects.mockResolvedValue([]);
    const cleanup = await mount(root, makeContext());
    expect(typeof cleanup).toBe('function');
  });
});
