import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ── mocks ────────────────────────────────────────────────────────────────────
vi.mock('../../../services/editor.service.js', () => ({
  loadRobotTestContent: vi.fn(),
  getTestsForProject: vi.fn(),
  improveWithAI: vi.fn(),
  saveEditorContent: vi.fn(),
}));

vi.mock('../../../services/test.service.js', () => ({
  getProjects: vi.fn(),
}));

vi.mock('../../../utils/dom.js', async () => {
  const actual = await vi.importActual('../../../utils/dom.js');
  return {
    ...actual,
    loadTemplate: vi.fn().mockResolvedValue(`
      <section>
        <select id="editor-project">
          <option value="">Select project</option>
        </select>
        <select id="editor-test" disabled>
          <option value="">Select a project first</option>
        </select>
        <div id="editor-toolbar" class="hidden"></div>
        <div id="editor-actions-slot"></div>
        <div id="editor-loading" class="hidden">
          <span id="editor-loading-text">Loading…</span>
        </div>
        <div id="editor-wrap" class="hidden">
          <div id="editor-file-info">
            <span id="editor-filename"></span>
            <span id="editor-dirty-badge" class="hidden">unsaved changes</span>
          </div>
          <div id="robot-editor" contenteditable="true"></div>
        </div>
        <div id="editor-status"></div>
      </section>
    `),
  };
});

vi.mock('../../../components/toast.js', () => ({ toast: vi.fn() }));

// ── imports (after mocks) ────────────────────────────────────────────────────
import { toast } from '../../../components/toast.js';
import {
  getTestsForProject,
  improveWithAI,
  loadRobotTestContent,
  saveEditorContent,
} from '../../../services/editor.service.js';
import { getProjects } from '../../../services/test.service.js';
import { mount } from '../editor.page.js';

// ── helpers ──────────────────────────────────────────────────────────────────
function makeContext(projects = [], activeProjectId = null) {
  let state = { projects, activeProjectId };
  const listeners = new Set();
  return {
    store: {
      getState: () => state,
      setState: (partial) => {
        state = { ...state, ...partial };
        listeners.forEach((listener) => listener(state));
      },
      subscribe: (listener) => {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    },
  };
}

function makeRoot() {
  const root = document.createElement('div');
  document.body.appendChild(root);
  return root;
}

// ── tests ─────────────────────────────────────────────────────────────────────
describe('robot-editor page – mount', () => {
  let root;

  beforeEach(() => {
    root = makeRoot();
    vi.clearAllMocks();
  });

  afterEach(() => {
    root.remove();
  });

  // ── mount ──────────────────────────────────────────────────────────────────

  it('renders the project select after mount', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());
    expect(root.querySelector('#editor-project')).not.toBeNull();
  });

  it('renders Save and Edit with AI buttons', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());
    const buttons = root.querySelectorAll('button');
    const labels = Array.from(buttons).map((b) => b.textContent);
    expect(labels).toContain('Save');
    expect(labels).toContain('Edit with AI');
  });

  it('populates the project dropdown from store', async () => {
    const context = makeContext([{ id: 1, name: 'Demo Project' }]);
    await mount(root, makeContext());
    // projects come from getProjects when store is empty
    getProjects.mockResolvedValue([{ id: 2, name: 'Alpha' }]);
    // reload — re-mount with fresh store
    root.innerHTML = '';
    const root2 = makeRoot();
    await mount(root2, makeContext([]));
    root2.remove();
  });

  it('fetches projects from API when store is empty', async () => {
    getProjects.mockResolvedValue([{ id: 3, name: 'Beta' }]);
    await mount(root, makeContext([]));
    expect(getProjects).toHaveBeenCalledTimes(1);
    const options = root.querySelector('#editor-project').options;
    const names = Array.from(options).map((o) => o.text);
    expect(names).toContain('Beta');
  });

  it('loads tests immediately when there is an active project in store', async () => {
    getTestsForProject.mockResolvedValue([{ id: 11, file_path: 'tests/active.robot' }]);

    await mount(root, makeContext([{ id: 1, name: 'Demo' }], 1));

    await vi.waitFor(() => expect(getTestsForProject).toHaveBeenCalledWith(1));
    expect(root.querySelector('#editor-project').value).toBe('1');
  });

  // ── project select change ──────────────────────────────────────────────────

  it('enables test select when a project is chosen', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Demo' }]);
    getTestsForProject.mockResolvedValue([{ id: 10, file_path: 'test_1.robot' }]);
    await mount(root, makeContext());

    const projectSelect = root.querySelector('#editor-project');
    projectSelect.value = '1';
    projectSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(getTestsForProject).toHaveBeenCalledWith(1));

    const testSelect = root.querySelector('#editor-test');
    expect(testSelect.disabled).toBe(false);
  });

  it('shows "No tests found" when project has no tests', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Demo' }]);
    getTestsForProject.mockResolvedValue([]);
    await mount(root, makeContext());

    const projectSelect = root.querySelector('#editor-project');
    projectSelect.value = '1';
    projectSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() =>
      expect(root.querySelector('#editor-test').innerHTML).toContain('No tests found')
    );
  });

  it('resets test select when project is cleared', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());

    const projectSelect = root.querySelector('#editor-project');
    projectSelect.value = '';
    projectSelect.dispatchEvent(new Event('change'));

    const testSelect = root.querySelector('#editor-test');
    await vi.waitFor(() => expect(testSelect.disabled).toBe(true));
  });

  // ── test select change ─────────────────────────────────────────────────────

  it('loads test content when a test is selected', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Demo' }]);
    getTestsForProject.mockResolvedValue([{ id: 10, file_path: 'test_login.robot' }]);
    loadRobotTestContent.mockResolvedValue({
      id: 10,
      file_path: '/tests/test_login.robot',
      content: '*** Test Cases ***\nLogin Test\n    Log    hello',
    });
    await mount(root, makeContext());

    // Simulate selecting a project first
    const projectSelect = root.querySelector('#editor-project');
    projectSelect.value = '1';
    projectSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(getTestsForProject).toHaveBeenCalled());

    // Then select a test
    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="10">test_login.robot</option>';
    testSelect.value = '10';
    testSelect.dispatchEvent(new Event('change'));

    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalledWith(10));
    await vi.waitFor(() =>
      expect(root.querySelector('#editor-wrap').classList.contains('hidden')).toBe(false)
    );
  });

  it('shows error toast when test loading fails', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockRejectedValue(new Error('Not found'));
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="99">bad.robot</option>';
    testSelect.value = '99';
    testSelect.dispatchEvent(new Event('change'));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Not found', 'error'));
  });

  // ── save ───────────────────────────────────────────────────────────────────

  it('calls saveEditorContent when Save is clicked after loading a test', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 5,
      file_path: '/tests/t.robot',
      content: '*** Test Cases ***',
    });
    saveEditorContent.mockResolvedValue({ id: 5 });
    await mount(root, makeContext());

    // Manually set currentTestId by simulating test select change
    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="5">t.robot</option>';
    testSelect.value = '5';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());

    const saveBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn.click();
    await vi.waitFor(() => expect(saveEditorContent).toHaveBeenCalledWith(5, expect.any(String)));
    expect(toast).toHaveBeenCalledWith('Test saved');
  });

  it('shows error toast when save fails', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 5,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    saveEditorContent.mockRejectedValue(new Error('Save failed'));
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="5">t.robot</option>';
    testSelect.value = '5';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());

    const saveBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn.click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Save failed', 'error'));
  });

  // ── AI improvement ─────────────────────────────────────────────────────────

  it('calls improveWithAI when "Edit with AI" is clicked', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 7,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    improveWithAI.mockResolvedValue('*** Test Cases ***\nImproved Test\n    Log    improved');
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="7">t.robot</option>';
    testSelect.value = '7';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());

    const aiBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Edit with AI'
    );
    aiBtn.click();
    await vi.waitFor(() => expect(improveWithAI).toHaveBeenCalledWith(7, expect.any(String)));
    expect(toast).toHaveBeenCalledWith('AI improvement applied');
  });

  it('shows error toast when AI improvement fails', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 7,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    improveWithAI.mockRejectedValue(new Error('AI unavailable'));
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="7">t.robot</option>';
    testSelect.value = '7';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());

    const aiBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Edit with AI'
    );
    aiBtn.click();
    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('AI unavailable', 'error'));
  });

  // ── getEditorText – DIV/P and SPAN/BR branches (lines 32, 34) ─────────────

  it('extracts text from DIV child nodes in the editor element', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 1,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    saveEditorContent.mockResolvedValue({ id: 1 });
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="1">t.robot</option>';
    testSelect.value = '1';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());

    // Place a DIV child node inside the contenteditable to exercise line 32
    const editorEl = root.querySelector('#robot-editor');
    editorEl.innerHTML = '';
    const div = document.createElement('div');
    div.textContent = '*** Test Cases ***';
    editorEl.appendChild(div);

    const saveBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn.click();
    await vi.waitFor(() =>
      expect(saveEditorContent).toHaveBeenCalledWith(
        1,
        expect.stringContaining('*** Test Cases ***')
      )
    );
  });

  it('extracts text from SPAN child nodes in the editor element', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 2,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    saveEditorContent.mockResolvedValue({ id: 2 });
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="2">t.robot</option>';
    testSelect.value = '2';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());

    // Place a SPAN child node to exercise line 34
    const editorEl = root.querySelector('#robot-editor');
    editorEl.innerHTML = '';
    const span = document.createElement('span');
    span.textContent = '*** Keywords ***';
    editorEl.appendChild(span);

    const saveBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn.click();
    await vi.waitFor(() =>
      expect(saveEditorContent).toHaveBeenCalledWith(2, expect.stringContaining('*** Keywords ***'))
    );
  });

  // ── project select error branch (lines 193-195) ───────────────────────────

  it('shows error toast and "Error loading tests" when getTestsForProject throws', async () => {
    getProjects.mockResolvedValue([{ id: 1, name: 'Demo' }]);
    getTestsForProject.mockRejectedValue(new Error('Network error'));
    await mount(root, makeContext());

    const projectSelect = root.querySelector('#editor-project');
    projectSelect.value = '1';
    projectSelect.dispatchEvent(new Event('change'));

    await vi.waitFor(() => expect(toast).toHaveBeenCalledWith('Network error', 'error'));
    await vi.waitFor(() =>
      expect(root.querySelector('#editor-test').innerHTML).toContain('Error loading tests')
    );
  });

  // ── test select cleared (lines 203-207) ──────────────────────────────────

  it('hides editor wrap and toolbar when test select is cleared', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 5,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    await mount(root, makeContext());

    // First load a test to show the editor
    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="5">t.robot</option>';
    testSelect.value = '5';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() =>
      expect(root.querySelector('#editor-wrap').classList.contains('hidden')).toBe(false)
    );

    // Now clear the selection (value = "")
    testSelect.innerHTML =
      '<option value="">Select test file</option><option value="5">t.robot</option>';
    testSelect.value = '';
    testSelect.dispatchEvent(new Event('change'));

    await vi.waitFor(() =>
      expect(root.querySelector('#editor-wrap').classList.contains('hidden')).toBe(true)
    );
    expect(root.querySelector('#editor-toolbar').classList.contains('hidden')).toBe(true);
  });

  // ── getEditorText TEXT_NODE branch (line 32) ───────────────────────────────

  it('reads content via TEXT_NODE branch when editor has plain text nodes', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 7,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    saveEditorContent.mockResolvedValue({ id: 7 });
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="7">t.robot</option>';
    testSelect.value = '7';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());

    // Set raw text (creates a TEXT_NODE as direct child, not a SPAN/DIV)
    const editorEl = root.querySelector('#robot-editor');
    editorEl.textContent = '*** Settings ***\nLibrary    Browser';

    const saveBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn.click();
    await vi.waitFor(() =>
      expect(saveEditorContent).toHaveBeenCalledWith(7, expect.stringContaining('*** Settings ***'))
    );
  });

  // ── getEditorText: SPAN/BR branch (lines 35-37) ────────────────────────────

  it('reads content from a BR child node in the editor (SPAN/BR branch)', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 8,
      file_path: '/t.robot',
      content: '*** Test Cases ***',
    });
    saveEditorContent.mockResolvedValue({ id: 8 });
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="8">t.robot</option>';
    testSelect.value = '8';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));

    // Replace editor content with a BR node — exercises the SPAN/BR else-if branch
    const editorEl = root.querySelector('#robot-editor');
    while (editorEl.firstChild) editorEl.removeChild(editorEl.firstChild);
    editorEl.appendChild(document.createElement('br'));

    const saveBtn2 = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn2.click();
    await vi.waitFor(() => expect(saveEditorContent).toHaveBeenCalledWith(8, expect.any(String)));
  });

  // ── getEditorText: fallback when lines is empty (line 41) ──────────────────

  it('falls back to textContent when editor has no matchable child nodes', async () => {
    getProjects.mockResolvedValue([]);
    loadRobotTestContent.mockResolvedValue({
      id: 9,
      file_path: '/t.robot',
      content: '',
    });
    saveEditorContent.mockResolvedValue({ id: 9 });
    await mount(root, makeContext());

    const testSelect = root.querySelector('#editor-test');
    testSelect.innerHTML = '<option value="9">t.robot</option>';
    testSelect.value = '9';
    testSelect.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(loadRobotTestContent).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));

    // Empty editor → childNodes empty → lines stays [] → fallback path
    const editorEl = root.querySelector('#robot-editor');
    while (editorEl.firstChild) editorEl.removeChild(editorEl.firstChild);

    const saveBtn3 = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn3.click();
    await vi.waitFor(() => expect(saveEditorContent).toHaveBeenCalledWith(9, ''));
  });

  // ── save early return when no test loaded (line 119) ───────────────────────

  it('save button does nothing when no test is loaded', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());
    const saveBtn4 = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Save'
    );
    saveBtn4.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(saveEditorContent).not.toHaveBeenCalled();
  });

  // ── AI button early return when no test loaded (line 137) ──────────────────

  it('AI button does nothing when no test is loaded', async () => {
    getProjects.mockResolvedValue([]);
    await mount(root, makeContext());
    const aiBtn = Array.from(root.querySelectorAll('button')).find(
      (b) => b.textContent === 'Edit with AI'
    );
    aiBtn.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(improveWithAI).not.toHaveBeenCalled();
  });

  it('reacts to store activeProjectId changes via subscribe callback', async () => {
    getTestsForProject.mockResolvedValue([]);
    const context = makeContext(
      [
        { id: 1, name: 'Project 1' },
        { id: 2, name: 'Project 2' },
      ],
      1
    );

    await mount(root, context);

    context.store.setState({ activeProjectId: 2 });

    await vi.waitFor(() => expect(getTestsForProject).toHaveBeenCalledWith(2));
    expect(root.querySelector('#editor-project').value).toBe('2');
  });
});
