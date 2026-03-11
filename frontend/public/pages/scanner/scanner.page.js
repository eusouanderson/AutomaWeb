import { toast } from '../../components/toast.js';
import {
  deleteGeneratedTestService,
  executeProjectTests,
  getProjectGeneratedTests,
  getProjects
} from '../../services/test.service.js';
import { formatDate } from '../../utils/helpers.js';

const SCANNER_STORAGE_FEEDBACK = 'scanner_feedback';

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

function extractExecutionMessage(data) {
  if (data?.error_output) {
    const firstLine = String(data.error_output)
      .split('\n')
      .find((line) => line.trim());
    return firstLine || 'A execucao dos testes falhou.';
  }

  if (Number(data?.failed || 0) > 0) {
    return `Execucao concluida com falhas: ${data.failed} teste(s) falharam.`;
  }

  return 'Testes executados com sucesso!';
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

  // Restore feedback textarea from localStorage
  if (executionFeedback) {
    executionFeedback.value = localStorage.getItem(SCANNER_STORAGE_FEEDBACK) || '';
  }
  executionFeedback?.addEventListener('input', () => {
    localStorage.setItem(SCANNER_STORAGE_FEEDBACK, executionFeedback.value);
  });

  const executeTestSelector = document.getElementById('execute-test-selector');
  const executeTestListCheck = document.getElementById('execute-test-list-check');
  const execSelectAllBtn = document.getElementById('exec-select-all');
  const execDeselectAllBtn = document.getElementById('exec-deselect-all');
  const execHeadlessCheckbox = document.getElementById('exec-headless');

  function getHeadless() {
    return execHeadlessCheckbox ? execHeadlessCheckbox.checked : true;
  }

  function getSelectedTestIds() {
    const checked = executeTestListCheck?.querySelectorAll('.exec-test-check:checked') ?? [];
    const ids = [...checked].map((cb) => Number(cb.value));
    return ids;
  }

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

  async function loadExecuteTests(projectId) {
    if (!executeTestSelector || !executeTestListCheck) return;

    if (!projectId) {
      executeTestSelector.classList.add('hidden');
      return;
    }

    executeTestSelector.classList.remove('hidden');
    executeTestListCheck.innerHTML = '<div class="loading">Carregando testes...</div>';

    try {
      const tests = await getProjectGeneratedTests(projectId);
      if (!tests.length) {
        executeTestListCheck.innerHTML =
          '<div class="empty">Nenhum teste gerado para este projeto.</div>';
        return;
      }

      executeTestListCheck.innerHTML = tests
        .map(
          (t) => `
          <label class="test-check-row">
            <input type="checkbox" class="exec-test-check" value="${t.id}" checked />
            <span class="test-check-name">${t.file_path.split('/').pop()}</span>
            <span class="test-check-id">#${t.id}</span>
          </label>
        `
        )
        .join('');
    } catch (_) {
      executeTestListCheck.innerHTML = '<div class="empty">Erro ao carregar testes.</div>';
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

  const EXEC_PHASES = [
    { id: 'prepare', label: 'Preparando ambiente' },
    { id: 'heal', label: 'Validando e curando testes (AI)' },
    { id: 'run', label: 'Executando testes Robot' },
    { id: 'report', label: 'Gerando relatórios' }
  ];

  function buildExecTracker() {
    executionLoading.innerHTML = `
      <p class="gen-title" id="exec-phase-title">Iniciando execução…</p>
      <ol class="gen-steps" role="list">
        ${EXEC_PHASES.map(
          (p) => `
          <li class="gen-step gen-step--idle" data-phase="${p.id}">
            <span class="gen-step-icon" aria-hidden="true"></span>
            <span class="gen-step-label">${p.label}</span>
          </li>
        `
        ).join('')}
      </ol>
    `;

    const phaseTitle = executionLoading.querySelector('#exec-phase-title');
    const getEl = (id) => executionLoading.querySelector(`[data-phase="${id}"]`);

    return {
      activate(phaseId) {
        const phase = EXEC_PHASES.find((p) => p.id === phaseId);
        if (phaseTitle && phase) phaseTitle.textContent = `${phase.label}…`;
        let found = false;
        for (const p of EXEC_PHASES) {
          const el = getEl(p.id);
          if (!el) continue;
          if (p.id === phaseId) {
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
        for (const p of EXEC_PHASES) {
          const el = getEl(p.id);
          if (el) el.className = 'gen-step gen-step--done';
        }
        if (phaseTitle) phaseTitle.textContent = 'Execução concluída';
      },
      error(phaseId) {
        const el = getEl(phaseId);
        if (el) el.className = 'gen-step gen-step--error';
        if (phaseTitle) phaseTitle.textContent = 'Execução falhou';
      }
    };
  }

  function renderTestCases(data) {
    const testListEl = document.getElementById('execution-test-list');
    if (!testListEl) return;

    const cases = data.test_cases;
    if (!cases?.length) {
      testListEl.innerHTML = '';
      return;
    }

    testListEl.innerHTML = cases
      .map((tc) => {
        const st = (tc.status || '').toUpperCase();
        const cls = st === 'PASS' ? 'pass' : st === 'FAIL' ? 'fail' : 'skip';
        const icon = st === 'PASS' ? '✅' : st === 'FAIL' ? '❌' : '⏭️';
        const msg = tc.message ? `<div class="exec-test-item-msg">${tc.message}</div>` : '';
        return `
          <div class="exec-test-item exec-test-item--${cls}">
            <span class="exec-test-item-status">${icon}</span>
            <div>
              <div class="exec-test-item-name">${tc.name}</div>
              ${msg}
            </div>
          </div>
        `;
      })
      .join('');
  }

  executeForm?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const projectId = Number.parseInt(executeProjectSelect.value, 10);
    const submitButton = executeForm.querySelector('button[type="submit"]');
    const originalLabel = submitButton.textContent;

    let tracker = null;
    let currentPhase = 'prepare';

    try {
      resetExecutionResult();
      submitButton.disabled = true;
      submitButton.textContent = 'Executando…';
      executionLoading.classList.remove('hidden');

      tracker = buildExecTracker();
      tracker.activate('prepare');

      const t1 = setTimeout(() => {
        currentPhase = 'heal';
        tracker.activate('heal');
      }, 3000);
      const t2 = setTimeout(() => {
        currentPhase = 'run';
        tracker.activate('run');
      }, 8000);

      const data = await executeProjectTests(projectId, getSelectedTestIds(), getHeadless());

      clearTimeout(t1);
      clearTimeout(t2);
      currentPhase = 'report';
      tracker.activate('report');
      await new Promise((r) => setTimeout(r, 600));
      tracker.complete();

      executionResult.style.display = 'block';
      statTotal.textContent = String(data.total_tests || 0);
      statPassed.textContent = String(data.passed || 0);
      statFailed.textContent = String(data.failed || 0);
      statSkipped.textContent = String(data.skipped || 0);

      renderTestCases(data);

      if (data.error_output) {
        executionError.textContent = data.error_output;
        executionError.style.display = 'block';
      }

      reportButton.dataset.reportPath = data.mkdocs_index || '';
      robotReportButton.dataset.reportPath = data.report_file || '';
      logButton.dataset.logPath = data.log_file || '';

      setRecreatePanel(data, projectId);

      const hasFailure =
        data.status === 'failed' || Number(data.failed || 0) > 0 || Boolean(data.error_output);

      toast(extractExecutionMessage(data), hasFailure ? 'error' : 'success');
      setTimeout(() => executionLoading.classList.add('hidden'), 1500);
    } catch (error) {
      if (tracker) tracker.error(currentPhase);
      toast(error.message, 'error');
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
    }
  });

  executeProjectSelect?.addEventListener('change', () => {
    resetExecutionResult();
    const projectId = Number.parseInt(executeProjectSelect.value, 10);
    loadExecuteTests(projectId);
  });

  execSelectAllBtn?.addEventListener('click', () => {
    executeTestListCheck?.querySelectorAll('.exec-test-check').forEach((cb) => (cb.checked = true));
  });

  execDeselectAllBtn?.addEventListener('click', () => {
    executeTestListCheck
      ?.querySelectorAll('.exec-test-check')
      .forEach((cb) => (cb.checked = false));
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
