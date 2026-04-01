import { createButton } from '../../components/button.js';
import { toast } from '../../components/toast.js';
import {
  getTestsForProject,
  improveWithAI,
  loadRobotTestContent,
  saveEditorContent,
} from '../../services/editor.service.js';
import { getProjects } from '../../services/test.service.js';
import { loadTemplate, qs, renderHTML } from '../../utils/dom.js';

const TEMPLATE_PATH = '/static/frontend/pages/robot-editor/editor.html';

/** Minimal syntax highlighter: adds CSS classes to Robot Framework sections. */
function highlightRobotSyntax(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^(\*{3}\s*.+?\s*\*{3})$/gm, '<span class="rf-section">$1</span>')
    .replace(/^(#.*)$/gm, '<span class="rf-comment">$1</span>')
    .replace(/(\${[^}]+}|@{[^}]+}|&{[^}]+})/g, '<span class="rf-variable">$1</span>');
}

/**
 * Extract plain text from a contenteditable element, preserving newlines.
 */
function getEditorText(el) {
  const lines = [];
  el.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      lines.push(node.textContent);
    } else if (node.nodeName === 'DIV' || node.nodeName === 'P') {
      lines.push(node.textContent);
    } else if (node.nodeName === 'SPAN' || node.nodeName === 'BR') {
      // inline span (highlight) — collect its text
      lines.push(node.textContent);
    }
  });
  // Fallback: if nothing came through child-walk, use innerText
  return lines.length ? lines.join('\n') : el.innerText || el.textContent || '';
}

/**
 * Set highlighted HTML into the contenteditable while preserving scroll position.
 * We set innerHTML directly; the user then edits plain text inside spans.
 * For simplicity we keep the non-highlighted raw content as the source of truth
 * (stored separately) and only apply highlighting on explicit "render" calls.
 */
function renderHighlighted(el, text) {
  const scrollTop = el.scrollTop;
  el.innerHTML = highlightRobotSyntax(text);
  el.scrollTop = scrollTop;
}

export async function mount(root, context) {
  const template = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, template);

  const projectSelect = qs('#editor-project', root);
  const testSelect = qs('#editor-test', root);
  const toolbar = qs('#editor-toolbar', root);
  const actionsSlot = qs('#editor-actions-slot', root);
  const loadingEl = qs('#editor-loading', root);
  const loadingText = qs('#editor-loading-text', root);
  const editorWrap = qs('#editor-wrap', root);
  const editorEl = qs('#robot-editor', root);
  const filenameEl = qs('#editor-filename', root);
  const dirtyBadge = qs('#editor-dirty-badge', root);
  const statusEl = qs('#editor-status', root);

  let currentTestId = null;
  let isDirty = false;

  // ── helpers ──────────────────────────────────────────────────────────────

  function setStatus(message, type = 'info') {
    statusEl.textContent = message;
    statusEl.className = `editor-status editor-status--${type}`;
  }

  function showLoading(message = 'Loading…') {
    loadingText.textContent = message;
    loadingEl.classList.remove('hidden');
    editorWrap.classList.add('hidden');
    toolbar.classList.add('hidden');
  }

  function hideLoading() {
    loadingEl.classList.add('hidden');
  }

  function markDirty() {
    if (!isDirty) {
      isDirty = true;
      dirtyBadge.classList.remove('hidden');
    }
  }

  function markClean() {
    isDirty = false;
    dirtyBadge.classList.add('hidden');
  }

  function setEditorContent(text) {
    renderHighlighted(editorEl, text);
    markClean();
  }

  // ── actions ──────────────────────────────────────────────────────────────

  const saveBtn = createButton({ label: 'Save', variant: 'primary' });
  const aiBtn = createButton({ label: 'Edit with AI', variant: 'secondary' });

  actionsSlot.appendChild(saveBtn);
  actionsSlot.appendChild(aiBtn);

  saveBtn.addEventListener('click', async () => {
    if (!currentTestId) return;
    saveBtn.disabled = true;
    setStatus('Saving…', 'info');
    try {
      const content = getEditorText(editorEl);
      await saveEditorContent(currentTestId, content);
      markClean();
      setStatus('Saved successfully.', 'success');
      toast('Test saved');
    } catch (error) {
      setStatus(error.message, 'error');
      toast(error.message, 'error');
    } finally {
      saveBtn.disabled = false;
    }
  });

  aiBtn.addEventListener('click', async () => {
    if (!currentTestId) return;
    aiBtn.disabled = true;
    setStatus('Sending to AI…', 'info');
    try {
      const content = getEditorText(editorEl);
      const improved = await improveWithAI(currentTestId, content);
      setEditorContent(improved);
      markDirty();
      setStatus('AI improvement applied. Review and save when ready.', 'success');
      toast('AI improvement applied');
    } catch (error) {
      setStatus(error.message, 'error');
      toast(error.message, 'error');
    } finally {
      aiBtn.disabled = false;
    }
  });

  // Track edits to mark dirty
  editorEl.addEventListener('input', markDirty);

  // ── project select ────────────────────────────────────────────────────────

  async function loadProjectsOptions() {
    let projects = context.store.getState().projects;
    if (!projects.length) {
      projects = await getProjects();
      context.store.setState({ projects });
    }
    projectSelect.innerHTML =
      '<option value="">Select project</option>' +
      projects.map((p) => `<option value="${p.id}">${p.name}</option>`).join('');

    const activeId = context.store.getState().activeProjectId;
    if (activeId) {
      projectSelect.value = String(activeId);
      projectSelect.dispatchEvent(new Event('change'));
    }
  }

  projectSelect.addEventListener('change', async () => {
    const projectId = Number(projectSelect.value);
    context.store.setState({ activeProjectId: projectId || null });
    if (!projectId) {
      testSelect.innerHTML = '<option value="">Select a project first</option>';
      testSelect.disabled = true;
      editorWrap.classList.add('hidden');
      toolbar.classList.add('hidden');
      currentTestId = null;
      return;
    }
    testSelect.disabled = false;
    testSelect.innerHTML = '<option value="">Loading tests…</option>';
    try {
      const tests = await getTestsForProject(projectId);
      if (!tests.length) {
        testSelect.innerHTML = '<option value="">No tests found for this project</option>';
        return;
      }
      testSelect.innerHTML =
        '<option value="">Select test file</option>' +
        tests.map((t) => `<option value="${t.id}">${t.file_path}</option>`).join('');
    } catch (error) {
      toast(error.message, 'error');
      testSelect.innerHTML = '<option value="">Error loading tests</option>';
    }
  });

  // ── test select ───────────────────────────────────────────────────────────

  testSelect.addEventListener('change', async () => {
    const testId = Number(testSelect.value);
    if (!testId) {
      editorWrap.classList.add('hidden');
      toolbar.classList.add('hidden');
      currentTestId = null;
      return;
    }

    showLoading('Loading test file…');
    currentTestId = testId;

    try {
      const test = await loadRobotTestContent(testId);
      filenameEl.textContent = test.file_path.split('/').pop();
      setEditorContent(test.content || '');
      hideLoading();
      editorWrap.classList.remove('hidden');
      toolbar.classList.remove('hidden');
      setStatus('', 'info');
    } catch (error) {
      hideLoading();
      setStatus(error.message, 'error');
      toast(error.message, 'error');
      currentTestId = null;
    }
  });

  await loadProjectsOptions();

  context.store.subscribe((state) => {
    const activeId = state.activeProjectId;
    const currentValue = Number(projectSelect.value) || null;
    if (activeId !== currentValue) {
      projectSelect.value = activeId ? String(activeId) : '';
      projectSelect.dispatchEvent(new Event('change'));
    }
  });
}
