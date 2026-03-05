import { createButton } from '../../components/button.js';
import { toast } from '../../components/toast.js';
import { runProjectScan } from '../../services/scan.service.js';
import { getProjects } from '../../services/test.service.js';
import { loadTemplate, qs, renderHTML } from '../../utils/dom.js';
import { escapeHtml } from '../../utils/helpers.js';

const TEMPLATE_PATH = '/static/frontend/pages/project-scan/scan.html';

export async function mount(root, context) {
  const template = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, template);

  const form = qs('#scan-form', root);
  const select = qs('#scan-project', root);
  const actionSlot = qs('#scan-action-slot', root);
  const progress = qs('#scan-progress', root);
  const summary = qs('#scan-summary', root);

  actionSlot.appendChild(createButton({ label: 'Start scan', type: 'submit', variant: 'primary' }));

  async function loadProjectsOptions() {
    let projects = context.store.getState().projects;
    if (!projects.length) {
      projects = await getProjects();
      context.store.setState({ projects });
    }

    select.innerHTML =
      '<option value="">Select project</option>' +
      projects
        .map(
          (project) =>
            `<option value="${project.id}" data-url="${project.url || ''}">${project.name}</option>`
        )
        .join('');
  }

  const onSubmit = async (event) => {
    event.preventDefault();
    progress.innerHTML = '';
    summary.textContent = 'Running scan...';

    const selected = select.options[select.selectedIndex];
    const projectUrl = selected?.dataset?.url;

    try {
      const result = await runProjectScan(projectUrl, {
        onProgress: (message) => {
          const line = document.createElement('p');
          line.textContent = `- ${message}`;
          progress.appendChild(line);
        },
        onError: (message) => {
          toast(message || 'Scan error', 'error');
        }
      });

      context.store.setState({ lastScanResult: result });
      const typeSummary = Object.entries(result?.summary || {})
        .map(([key, total]) => `${key}: ${total}`)
        .join(', ');

      summary.innerHTML = `
        <p><strong>Title:</strong> ${escapeHtml(result?.title || '-')}</p>
        <p><strong>Total elements:</strong> ${Number(result?.total_elements || 0)}</p>
        <p><strong>Elements by type:</strong> ${escapeHtml(typeSummary || '-')}</p>
      `;
      toast('Scan finished');
    } catch (error) {
      summary.textContent = error.message;
      toast(error.message, 'error');
    }
  };

  form.addEventListener('submit', onSubmit);
  await loadProjectsOptions();

  return () => {
    form.removeEventListener('submit', onSubmit);
  };
}
