import { toast } from '../../components/toast.js';
import {
  deleteGeneratedTestService,
  executeProjectTests,
  getProjectGeneratedTests,
  getProjects
} from '../../services/test.service.js';
import { formatDate } from '../../utils/helpers.js';

function buildExecutionFeedback(data) {
  let lines = [
    'A execucao dos testes apresentou falhas. Recrie o teste Robot Framework corrigindo os problemas abaixo.',
    '',
    `Resumo: total=${data.total_tests}, passed=${data.passed}, failed=${data.failed}, skipped=${data.skipped}`
  ];

  if (data.error_output) {
    lines = lines.concat(['', 'Saida de erro da execucao:', data.error_output]);
  }

  lines = lines.concat([
    '',
    'Objetivo: Corrigir os testes Robot Framework com base nos erros de execucao.'
  ]);

  return lines.join('\n').slice(0, 6000);
}

export function initScannerPage({ onRecreateRequested }) {
  const testsProjectSelect = document.getElementById('tests-project');
  const testsList = document.getElementById('tests-list');

  const executeForm = document.getElementById('execute-tests-form');
  const executeProjectSelect = document.getElementById('execute-project');
  const executionLoading = document.getElementById('execution-loading');
  const executionResult = document.getElementById('execution-result');
  const executionError = document.getElementById('execution-error');

  const statTotal = document.getElementById('stat-total');
  const statPassed = document.getElementById('stat-passed');
  const statFailed = document.getElementById('stat-failed');
  const statSkipped = document.getElementById('stat-skipped');

  const reportButton = document.getElementById('view-report-btn');
  const robotReportButton = document.getElementById('view-robot-report-btn');
  const logButton = document.getElementById('view-log-btn');

  const recreatePanel = document.getElementById('recreate-panel');
  const recreateButton = document.getElementById('recreate-test-btn');
  const executionFeedback = document.getElementById('execution-feedback');

  function resetExecutionResult() {
    executionResult.style.display = 'none';
    statTotal.textContent = '0';
    statPassed.textContent = '0';
    statFailed.textContent = '0';
    statSkipped.textContent = '0';

    executionError.textContent = '';
    executionError.style.display = 'none';

    reportButton.dataset.reportPath = '';
    robotReportButton.dataset.reportPath = '';
    logButton.dataset.logPath = '';

    recreatePanel.classList.add('hidden');
    executionFeedback.value = '';
    recreateButton.dataset.projectId = '';
  }

  function setRecreatePanel(data, projectId) {
    const hasFailure = Number(data.failed || 0) > 0 || Boolean(data.error_output);

    if (!hasFailure) {
      recreatePanel.classList.add('hidden');
      executionFeedback.value = '';
      recreateButton.dataset.projectId = '';
      return;
    }

    recreatePanel.classList.remove('hidden');
    executionFeedback.value = buildExecutionFeedback(data);
    recreateButton.dataset.projectId = String(projectId);
  }

  async function loadGeneratedTests(projectId) {
    if (!testsList) {
      return;
    }

    if (!projectId) {
      testsList.innerHTML = '<div class="empty">Selecione um projeto</div>';
      return;
    }

    testsList.innerHTML = '<div class="loading">Carregando testes...</div>';

    try {
      const tests = await getProjectGeneratedTests(projectId);

      if (!tests.length) {
        testsList.innerHTML = '<div class="empty">Nenhum teste gerado para este projeto</div>';
        return;
      }

      testsList.innerHTML = tests
        .map(
          (test) => `
            <div class="list-item">
              <div>
                <h3>${test.file_path}</h3>
                <small>ID do teste: ${test.id} | Criado em: ${formatDate(test.created_at)}</small>
              </div>
              <div>
                <button class="btn btn-secondary" data-test-download="${test.id}">Download</button>
                <button class="btn btn-danger" data-test-delete="${test.id}" data-project-id="${projectId}">Excluir</button>
              </div>
            </div>
          `
        )
        .join('');
    } catch (error) {
      testsList.innerHTML = '<div class="empty">Erro ao carregar testes</div>';
      toast(error.message, 'error');
    }
  }

  async function loadTestsProjects() {
    if (!testsProjectSelect || !testsList) {
      return;
    }

    testsList.innerHTML = '<div class="loading">Carregando projetos...</div>';

    try {
      const projects = await getProjects();
      testsProjectSelect.innerHTML =
        '<option value="">Selecione um projeto...</option>' +
        projects
          .map((project) => `<option value="${project.id}">${project.name}</option>`)
          .join('');

      if (!projects.length) {
        testsList.innerHTML = '<div class="empty">Nenhum projeto criado ainda</div>';
        return;
      }

      const selectedId = Number.parseInt(testsProjectSelect.value, 10);
      const projectId = selectedId || projects[0].id;
      testsProjectSelect.value = String(projectId);
      await loadGeneratedTests(projectId);
    } catch (error) {
      testsList.innerHTML = '<div class="empty">Erro ao carregar projetos</div>';
      toast(error.message, 'error');
    }
  }

  async function loadExecuteProjects() {
    if (!executeProjectSelect) {
      return;
    }

    try {
      const projects = await getProjects();
      executeProjectSelect.innerHTML = '<option value="">Selecione um projeto...</option>';

      projects.forEach((project) => {
        const option = document.createElement('option');
        option.value = String(project.id);
        option.textContent = project.test_directory
          ? `${project.name} (${project.test_directory})`
          : project.name;
        executeProjectSelect.appendChild(option);
      });

      resetExecutionResult();
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  testsProjectSelect?.addEventListener('change', async (event) => {
    const projectId = Number.parseInt(event.target.value, 10);
    await loadGeneratedTests(projectId);
  });

  testsList?.addEventListener('click', async (event) => {
    const downloadButton = event.target.closest('[data-test-download]');
    if (downloadButton) {
      globalThis.open(`/tests/${downloadButton.dataset.testDownload}/download`, '_blank');
      return;
    }

    const deleteButton = event.target.closest('[data-test-delete]');
    if (!deleteButton) {
      return;
    }

    if (!globalThis.confirm('Tem certeza que deseja excluir este teste gerado?')) {
      return;
    }

    try {
      await deleteGeneratedTestService(Number(deleteButton.dataset.testDelete));
      toast('Teste excluido com sucesso!');
      await loadGeneratedTests(Number(deleteButton.dataset.projectId));
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  executeForm?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const projectId = Number.parseInt(executeProjectSelect.value, 10);
    const submitButton = executeForm.querySelector('button[type="submit"]');
    const originalLabel = submitButton.textContent;

    try {
      resetExecutionResult();
      submitButton.disabled = true;
      submitButton.textContent = 'Executando...';
      executionLoading.classList.remove('hidden');

      const data = await executeProjectTests(projectId);

      executionResult.style.display = 'block';
      statTotal.textContent = String(data.total_tests || 0);
      statPassed.textContent = String(data.passed || 0);
      statFailed.textContent = String(data.failed || 0);
      statSkipped.textContent = String(data.skipped || 0);

      if (data.error_output) {
        executionError.textContent = data.error_output;
        executionError.style.display = 'block';
      }

      reportButton.dataset.reportPath = data.mkdocs_index || '';
      robotReportButton.dataset.reportPath = data.report_file || '';
      logButton.dataset.logPath = data.log_file || '';

      setRecreatePanel(data, projectId);
      toast('Testes executados com sucesso!');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
      executionLoading.classList.add('hidden');
    }
  });

  executeProjectSelect?.addEventListener('change', () => {
    resetExecutionResult();
  });

  recreateButton?.addEventListener('click', async () => {
    const projectId = Number.parseInt(recreateButton.dataset.projectId, 10);
    const feedback = executionFeedback.value;

    if (!projectId) {
      toast('Nao foi possivel identificar o projeto da execucao.', 'error');
      return;
    }

    if (!feedback.trim()) {
      toast('Adicione um feedback para enviar a IA.', 'error');
      return;
    }

    const originalLabel = recreateButton.textContent;
    try {
      recreateButton.disabled = true;
      recreateButton.textContent = 'Recriando...';
      await onRecreateRequested?.({ projectId, feedback });
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      recreateButton.disabled = false;
      recreateButton.textContent = originalLabel;
    }
  });

  reportButton?.addEventListener('click', () => {
    if (reportButton.dataset.reportPath) {
      globalThis.open(reportButton.dataset.reportPath, '_blank');
    }
  });

  robotReportButton?.addEventListener('click', () => {
    if (robotReportButton.dataset.reportPath) {
      globalThis.open(robotReportButton.dataset.reportPath, '_blank');
    }
  });

  logButton?.addEventListener('click', () => {
    if (logButton.dataset.logPath) {
      globalThis.open(logButton.dataset.logPath, '_blank');
    }
  });

  return {
    loadTestsProjects,
    loadExecuteProjects
  };
}
