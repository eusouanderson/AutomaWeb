import { toast } from '../../components/toast.js';
import { getProjectExecutions, getProjects } from '../../services/test.service.js';
import { loadTemplate, renderHTML } from '../../utils/dom.js';
import { escapeHtml, formatDate } from '../../utils/helpers.js';

const TEMPLATE_PATH = '/static/frontend/pages/reports/reports.html';

export async function mount(root, { store }) {
  const html = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, html);
  return initReportsPage({ store });
}

export function initReportsPage({ store }) {
  const projectSelect = document.getElementById('reports-project');
  const reportsList = document.getElementById('reports-list');

  if (!projectSelect || !reportsList) {
    return { loadReportsProjects: async () => {} };
  }

  function statusBadge(status) {
    const map = {
      completed: { cls: 'badge-pass', label: '✅ Concluído' },
      failed: { cls: 'badge-fail', label: '❌ Falhou' },
      running: { cls: 'badge-skip', label: '⏳ Executando' },
    };
    const { cls, label } = map[status] || { cls: 'badge-skip', label: status };
    return `<span class="exec-badge ${cls}">${label}</span>`;
  }

  function renderExecutions(executions) {
    if (!executions.length) {
      reportsList.innerHTML =
        '<div class="empty">Nenhuma execução encontrada para este projeto</div>';
      return;
    }

    reportsList.innerHTML = executions
      .map(
        (ex) => `
        <div class="list-item report-item">
          <div class="report-item-info">
            <div class="report-item-header">
              ${statusBadge(ex.status)}
              <span class="report-item-date">${formatDate(ex.created_at)}</span>
            </div>
            <div class="test-stats report-stats">
              <div class="stat-item">
                <span class="stat-label">Total</span>
                <span>${ex.total_tests ?? 0}</span>
              </div>
              <div class="stat-item stat-pass">
                <span class="stat-label">✅ Passou</span>
                <span>${ex.passed ?? 0}</span>
              </div>
              <div class="stat-item stat-fail">
                <span class="stat-label">❌ Falhou</span>
                <span>${ex.failed ?? 0}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">⏭️ Pulado</span>
                <span>${ex.skipped ?? 0}</span>
              </div>
            </div>
            ${
              ex.error_output
                ? `<details class="report-error-details">
                    <summary>Ver erros</summary>
                    <pre class="report-error-pre">${escapeHtml(ex.error_output)}</pre>
                  </details>`
                : ''
            }
          </div>
          <div class="report-item-actions">
            ${ex.mkdocs_index ? `<button class="btn btn-primary" data-open="${escapeHtml(ex.mkdocs_index)}">📊 MkDocs</button>` : ''}
            ${ex.report_file ? `<button class="btn btn-secondary" data-open="${escapeHtml(ex.report_file)}">🤖 Report</button>` : ''}
            ${ex.log_file ? `<button class="btn btn-secondary" data-open="${escapeHtml(ex.log_file)}">📝 Log</button>` : ''}
          </div>
        </div>
      `
      )
      .join('');
  }

  async function loadExecutions(projectId) {
    reportsList.innerHTML = '<div class="loading">Carregando relatórios...</div>';
    try {
      const executions = await getProjectExecutions(projectId);
      renderExecutions(executions);
    } catch (error) {
      reportsList.innerHTML = '<div class="empty">Erro ao carregar relatórios</div>';
      toast(error.message, 'error');
    }
  }

  async function loadReportsProjects() {
    try {
      let projects = store.getState().projects;
      if (!projects?.length) {
        projects = await getProjects();
        store.setState({ projects });
      }

      projectSelect.innerHTML =
        '<option value="">Selecione um projeto...</option>' +
        projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');

      const activeId = store.getState().activeProjectId;
      if (activeId) {
        projectSelect.value = String(activeId);
        await loadExecutions(activeId);
      } else {
        reportsList.innerHTML =
          '<div class="empty">Selecione um projeto para ver os relatórios</div>';
      }
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  projectSelect.addEventListener('change', async (event) => {
    const projectId = Number.parseInt(event.target.value, 10);
    store.setState({ activeProjectId: projectId || null });
    if (!projectId) {
      reportsList.innerHTML =
        '<div class="empty">Selecione um projeto para ver os relatórios</div>';
      return;
    }
    await loadExecutions(projectId);
  });

  reportsList.addEventListener('click', (event) => {
    const button = event.target.closest('[data-open]');
    if (button?.dataset?.open) {
      globalThis.open(button.dataset.open, '_blank');
    }
  });

  return { loadReportsProjects };
}
