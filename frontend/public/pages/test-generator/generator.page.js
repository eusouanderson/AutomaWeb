import { createButton } from '../../components/button.js';
import { createModal } from '../../components/modal.js';
import { toast } from '../../components/toast.js';
import { generateTestFromPrompt, getProjects } from '../../services/test.service.js';
import { loadTemplate, qs, renderHTML } from '../../utils/dom.js';

const TEMPLATE_PATH = '/static/frontend/pages/test-generator/generator.html';

const GEN_STEPS = [
  { id: 'analyze', label: 'Analyzing page context' },
  { id: 'generate', label: 'Generating test with AI' },
  { id: 'validate', label: 'Validating & healing' },
  { id: 'finalize', label: 'Finalizing' }
];

function buildProgressTracker(container) {
  container.innerHTML = `
    <p class="gen-title">Generating test…</p>
    <ol class="gen-steps" role="list">
      ${GEN_STEPS.map(
        (s) => `
        <li class="gen-step gen-step--idle" data-step="${s.id}">
          <span class="gen-step-icon" aria-hidden="true"></span>
          <span class="gen-step-label">${s.label}</span>
        </li>
      `
      ).join('')}
    </ol>
  `;

  const getEl = (id) => container.querySelector(`[data-step="${id}"]`);

  return {
    activate(stepId) {
      let found = false;
      for (const step of GEN_STEPS) {
        const el = getEl(step.id);
        if (!el) continue;
        if (step.id === stepId) {
          el.className = 'gen-step gen-step--active';
          found = true;
        } else if (!found) {
          el.className = 'gen-step gen-step--done';
        } else {
          el.className = 'gen-step gen-step--idle';
        }
      }
    },
    complete() {
      for (const step of GEN_STEPS) {
        const el = getEl(step.id);
        if (el) el.className = 'gen-step gen-step--done';
      }
      const title = container.querySelector('.gen-title');
      if (title) title.textContent = 'Test generated';
    },
    error(stepId) {
      const el = getEl(stepId);
      if (el) el.className = 'gen-step gen-step--error';
      const title = container.querySelector('.gen-title');
      if (title) title.textContent = 'Generation failed';
    }
  };
}

const STORAGE_KEY_PROMPT = 'generator_prompt';
const STORAGE_KEY_CONTEXT = 'generator_context';

export async function mount(root, context) {
  const template = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, template);

  const form = qs('#generator-form', root);
  const select = qs('#generator-project', root);
  const actions = qs('#generator-actions', root);
  const outputActions = qs('#generated-output-actions', root);
  const output = qs('#generated-output', root);
  const codeBlock = qs('#generated-code', root);
  const progressEl = qs('#generation-progress', root);

  const promptInput = qs('#generator-prompt', root);
  const contextInput = qs('#generator-context', root);

  // Restore saved values from localStorage
  if (promptInput) promptInput.value = localStorage.getItem(STORAGE_KEY_PROMPT) || '';
  if (contextInput) contextInput.value = localStorage.getItem(STORAGE_KEY_CONTEXT) || '';

  // Persist values on each keystroke
  promptInput?.addEventListener('input', () => {
    localStorage.setItem(STORAGE_KEY_PROMPT, promptInput.value);
  });
  contextInput?.addEventListener('input', () => {
    localStorage.setItem(STORAGE_KEY_CONTEXT, contextInput.value);
  });

  const helpModal = createModal({
    title: 'Prompt tips',
    content: `
      <ul>
        <li>Describe the user flow with clear steps.</li>
        <li>List expected validations in each step.</li>
        <li>Include edge cases and negative checks.</li>
      </ul>
    `
  });

  root.appendChild(helpModal.element);

  const submitBtn = createButton({ label: 'Generate test', type: 'submit', variant: 'primary' });
  actions.appendChild(submitBtn);
  actions.appendChild(
    createButton({ label: 'Prompt tips', variant: 'ghost', onClick: () => helpModal.open() })
  );

  outputActions.appendChild(
    createButton({
      label: 'Copy code',
      variant: 'secondary',
      onClick: async () => {
        await navigator.clipboard.writeText(codeBlock.textContent || '');
        toast('Code copied');
      }
    })
  );

  async function loadProjectsOptions() {
    let projects = context.store.getState().projects;
    if (!projects.length) {
      projects = await getProjects();
      context.store.setState({ projects });
    }

    select.innerHTML =
      '<option value="">Select project</option>' +
      projects.map((project) => `<option value="${project.id}">${project.name}</option>`).join('');
  }

  const onSubmit = async (event) => {
    event.preventDefault();

    submitBtn.disabled = true;
    output.classList.add('hidden');
    progressEl.classList.remove('hidden');

    const tracker = buildProgressTracker(progressEl);
    tracker.activate('analyze');

    let currentStep = 'analyze';
    const step2Timer = setTimeout(() => {
      currentStep = 'generate';
      tracker.activate('generate');
    }, 2500);

    try {
      const result = await generateTestFromPrompt({
        projectId: Number(select.value),
        prompt: promptInput.value,
        context: contextInput.value
      });

      clearTimeout(step2Timer);
      tracker.activate('validate');
      await new Promise((r) => setTimeout(r, 500));
      tracker.activate('finalize');
      await new Promise((r) => setTimeout(r, 400));
      tracker.complete();

      context.store.setState({ lastGeneratedTest: result });
      codeBlock.textContent = result.content || '';
      output.classList.remove('hidden');
      setTimeout(() => progressEl.classList.add('hidden'), 1200);
      toast('Test generated successfully');
    } catch (error) {
      clearTimeout(step2Timer);
      tracker.error(currentStep);
      toast(error.message, 'error');
    } finally {
      submitBtn.disabled = false;
    }
  };

  form.addEventListener('submit', onSubmit);
  await loadProjectsOptions();

  return () => {
    form.removeEventListener('submit', onSubmit);
    helpModal.element.remove();
  };
}

export function createLoader(label = 'Loading...') {
  const wrapper = document.createElement('div');
  wrapper.className = 'loader';
  wrapper.innerHTML = `<span class="loader-dot" aria-hidden="true"></span><span>${label}</span>`;
  return wrapper;
}
