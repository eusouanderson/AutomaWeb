import { createButton } from '../../components/button.js';
import { createModal } from '../../components/modal.js';
import { toast } from '../../components/toast.js';
import { generateTestFromPrompt, getProjects } from '../../services/test.service.js';
import { loadTemplate, qs, renderHTML } from '../../utils/dom.js';

const TEMPLATE_PATH = '/static/frontend/pages/test-generator/generator.html';

export async function mount(root, context) {
  const template = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, template);

  const form = qs('#generator-form', root);
  const select = qs('#generator-project', root);
  const actions = qs('#generator-actions', root);
  const outputActions = qs('#generated-output-actions', root);
  const output = qs('#generated-output', root);
  const codeBlock = qs('#generated-code', root);

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

  actions.appendChild(createButton({ label: 'Generate test', type: 'submit', variant: 'primary' }));
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

    try {
      const result = await generateTestFromPrompt({
        projectId: Number(select.value),
        prompt: qs('#generator-prompt', root).value,
        context: qs('#generator-context', root).value
      });

      context.store.setState({ lastGeneratedTest: result });
      codeBlock.textContent = result.content || '';
      output.classList.remove('hidden');
      toast('Test generated');
    } catch (error) {
      toast(error.message, 'error');
    }
  };

  form.addEventListener('submit', onSubmit);
  await loadProjectsOptions();

  return () => {
    form.removeEventListener('submit', onSubmit);
    helpModal.element.remove();
  };
}
