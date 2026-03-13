import { toast } from '../../components/toast.js';
import {
  createProjectService,
  deleteProjectService,
  getProjects
} from '../../services/test.service.js';
import { loadTemplate, renderHTML } from '../../utils/dom.js';
import { escapeHtml, formatDate } from '../../utils/helpers.js';

const TEMPLATE_PATH = '/static/frontend/pages/dashboard/dashboard.html';

export async function mount(root, { store }) {
  const html = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, html);
  return initDashboardPage({ store });
}

export function initDashboardPage({ store }) {
  const form = document.getElementById('create-project-form');
  const list = document.getElementById('projects-list');

  if (!form || !list) {
    return {
      loadProjects: async () => {}
    };
  }

  async function loadProjects() {
    list.innerHTML = '<div class="loading">Carregando projetos...</div>';

    try {
      const projects = await getProjects();
      store.setState({ projects });

      if (!projects.length) {
        list.innerHTML = '<div class="empty">Nenhum projeto criado ainda</div>';
        return;
      }

      list.innerHTML = projects
        .map(
          (project) => `
            <div class="list-item">
              <div>
                <h3>${escapeHtml(project.name)}</h3>
                <p>${escapeHtml(project.description || 'Sem descrição')}</p>
                <small>URL: ${escapeHtml(project.url || 'Não definida')}</small><br />
                <small>ID: ${project.id} | Criado em: ${formatDate(project.created_at)}</small>
              </div>
              <button class="btn btn-danger" data-project-id="${project.id}">🗑️ Deletar</button>
            </div>
          `
        )
        .join('');
    } catch (error) {
      list.innerHTML = '<div class="empty">Erro ao carregar projetos</div>';
      toast(error.message, 'error');
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    try {
      await createProjectService({
        name: document.getElementById('project-name').value,
        description: document.getElementById('project-description').value,
        url: document.getElementById('project-url').value,
        test_directory: document.getElementById('project-test-dir').value
      });

      form.reset();
      toast('Projeto criado com sucesso!');
      await loadProjects();
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  list.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-project-id]');
    if (!button) {
      return;
    }

    const projectId = Number(button.dataset.projectId);
    if (!projectId) {
      return;
    }

    if (!globalThis.confirm('Tem certeza que deseja deletar este projeto?')) {
      return;
    }

    try {
      await deleteProjectService(projectId);
      toast('Projeto deletado com sucesso!');
      await loadProjects();
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  return { loadProjects };
}
