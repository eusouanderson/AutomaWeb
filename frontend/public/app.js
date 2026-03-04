// API Base URL
const API_URL = '';
let lastScanByProject = new Map();
let isScanning = false;

// Utility: Show Toast
function showToast(message, type = 'success') {
  Toastify({
    text: message,
    duration: 3000,
    gravity: 'top',
    position: 'right',
    backgroundColor: type === 'success' ? '#10b981' : '#ef4444'
  }).showToast();
}

// Utility: Format Date
function formatDate(dateString) {
  return new Date(dateString).toLocaleString('pt-BR');
}

// Create Project
document.getElementById('create-project-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const name = document.getElementById('project-name').value;
  const description = document.getElementById('project-description').value;
  const url = document.getElementById('project-url').value;
  const test_directory = document.getElementById('project-test-dir').value;

  try {
    await axios.post(`${API_URL}/projects`, { name, description, url, test_directory });
    showToast('Projeto criado com sucesso!');
    e.target.reset();
    loadProjects();
  } catch (error) {
    showToast(error.response?.data?.detail || 'Erro ao criar projeto', 'error');
  }
});

// Delete Project
async function deleteProject(id, name) {
  if (!confirm(`Tem certeza que deseja deletar o projeto "${name}"?`)) {
    return;
  }

  try {
    await axios.delete(`${API_URL}/projects/${id}`);
    showToast('Projeto deletado com sucesso!');
    loadProjects();
    loadProjectsDropdown();
  } catch (error) {
    showToast(error.response?.data?.detail || 'Erro ao deletar projeto', 'error');
  }
}

// Load Projects
async function loadProjects() {
  const list = document.getElementById('projects-list');
  list.innerHTML = '<div class="loading">Carregando projetos...</div>';

  try {
    const { data } = await axios.get(`${API_URL}/projects`);

    if (data.length === 0) {
      list.innerHTML = '<div class="empty">Nenhum projeto criado ainda</div>';
      return;
    }

    list.innerHTML = data
      .map(
        (project) => `
            <div class="list-item">
                <div>
                    <h3>${project.name}</h3>
                    <p>${project.description || 'Sem descrição'}</p>
                    <small>URL: ${project.url || 'Não definida'}</small><br />
                    <small>ID: ${project.id} | Criado em: ${formatDate(project.created_at)}</small>
                </div>
                <button class="btn btn-danger" onclick="deleteProject(${project.id}, '${project.name}')" style="margin-left: auto;">🗑️ Deletar</button>
            </div>
        `
      )
      .join('');
  } catch (error) {
    list.innerHTML = '<div class="empty">Erro ao carregar projetos</div>';
    showToast('Erro ao carregar projetos', 'error');
  }
}

// Load Projects Dropdown
async function loadProjectsDropdown() {
  const select = document.getElementById('test-project');

  try {
    const { data } = await axios.get(`${API_URL}/projects`);

    select.innerHTML =
      '<option value="">Selecione um projeto</option>' +
      data
        .map((p) => `<option value="${p.id}" data-url="${p.url || ''}">${p.name}</option>`)
        .join('');
  } catch (error) {
    showToast('Erro ao carregar projetos', 'error');
  }
}

function resetScanPanel() {
  document.getElementById('scan-panel').classList.add('hidden');
  document.getElementById('scan-summary').classList.add('hidden');
  document.getElementById('scan-live-status').classList.add('hidden');
  document.getElementById('scan-ready-message').classList.add('hidden');
  document.getElementById('scan-progress').innerHTML = '';
  document.getElementById('scan-title').textContent = '-';
  document.getElementById('scan-total').textContent = '0';
  document.getElementById('scan-types').textContent = '-';
}

function setScanLoading(active) {
  const status = document.getElementById('scan-live-status');
  const ready = document.getElementById('scan-ready-message');
  const scanButton = document.getElementById('scan-page-btn');
  const statusText = document.getElementById('scan-live-text');

  if (active) {
    statusText.textContent = 'Escaneando';
    status.classList.remove('hidden');
    ready.classList.add('hidden');
    scanButton.disabled = true;
    return;
  }

  status.classList.add('hidden');
  scanButton.disabled = false;
}

function setScanReady(active) {
  const ready = document.getElementById('scan-ready-message');
  if (active) {
    ready.classList.remove('hidden');
  } else {
    ready.classList.add('hidden');
  }
}

function appendScanProgress(message) {
  const progress = document.getElementById('scan-progress');
  const line = document.createElement('div');
  line.className = 'scan-progress-line';
  line.textContent = `• ${message}`;
  progress.appendChild(line);
  progress.scrollTop = progress.scrollHeight;
}

async function scanSelectedProject() {
  if (isScanning) {
    return;
  }

  const select = document.getElementById('test-project');
  const projectId = parseInt(select.value);
  const selectedOption = select.options[select.selectedIndex];
  const projectUrl = selectedOption?.dataset?.url;

  if (!projectId) {
    showToast('Selecione um projeto antes de escanear.', 'error');
    return;
  }

  if (!projectUrl) {
    showToast('Projeto sem URL. Edite/crie um projeto com URL válida.', 'error');
    return;
  }

  resetScanPanel();
  document.getElementById('scan-panel').classList.remove('hidden');
  setScanLoading(true);
  setScanReady(false);
  isScanning = true;
  appendScanProgress('Iniciando escaneamento...');

  try {
    const response = await fetch(`${API_URL}/scan`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ url: projectUrl })
    });

    if (!response.ok || !response.body) {
      throw new Error('Falha ao iniciar stream de scan');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      events.forEach((eventBlock) => {
        const dataLine = eventBlock.split('\n').find((line) => line.startsWith('data: '));
        if (!dataLine) return;

        const payload = JSON.parse(dataLine.slice(6));
        if (payload.type === 'progress') {
          appendScanProgress(payload.message);
          return;
        }

        if (payload.type === 'result') {
          const result = payload.data;
          lastScanByProject.set(projectId, result);
          document.getElementById('scan-summary').classList.remove('hidden');
          document.getElementById('scan-title').textContent = result.title || '-';
          document.getElementById('scan-total').textContent = String(result.total_elements || 0);
          const summaryText = Object.entries(result.summary || {})
            .map(([key, count]) => `${key}: ${count}`)
            .join(', ');
          document.getElementById('scan-types').textContent = summaryText || '-';
          appendScanProgress('Dados estruturados prontos para geração de teste.');
          setScanLoading(false);
          setScanReady(true);
          showToast('Scan concluído com sucesso!');
          return;
        }

        if (payload.type === 'error') {
          appendScanProgress(`Erro: ${payload.message}`);
          setScanLoading(false);
          setScanReady(false);
          showToast(payload.message || 'Erro no scan', 'error');
        }
      });
    }
  } catch (error) {
    setScanLoading(false);
    setScanReady(false);
    showToast(error.message || 'Erro ao escanear página', 'error');
  } finally {
    isScanning = false;
    setScanLoading(false);
  }
}

document.getElementById('scan-page-btn').addEventListener('click', scanSelectedProject);
document.getElementById('test-project').addEventListener('change', () => {
  resetScanPanel();
});

// Generate Test
document.getElementById('generate-test-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const projectId = parseInt(document.getElementById('test-project').value);
  const prompt = document.getElementById('test-prompt').value;
  const context = document.getElementById('test-context').value;

  const resultSection = document.getElementById('generated-result');
  const codeElement = document.getElementById('test-code');

  resultSection.classList.add('hidden');

  if (!lastScanByProject.get(projectId)) {
    showToast('Execute o scan da página antes de gerar o teste.', 'error');
    return;
  }

  try {
    showToast('Gerando teste... Aguarde.', 'success');

    const { data } = await axios.post(`${API_URL}/tests/generate`, {
      project_id: projectId,
      prompt,
      context: context || null
    });

    codeElement.textContent = data.content;
    resultSection.classList.remove('hidden');

    // Store test ID for download
    document.getElementById('download-test-btn').dataset.testId = data.id;

    showToast('Teste gerado com sucesso!');
  } catch (error) {
    showToast(error.response?.data?.detail || 'Erro ao gerar teste', 'error');
  }
});

// Copy Test Code
document.getElementById('copy-test-btn').addEventListener('click', () => {
  const code = document.getElementById('test-code').textContent;
  navigator.clipboard.writeText(code);
  showToast('Código copiado!');
});

// Download Test
document.getElementById('download-test-btn').addEventListener('click', () => {
  const testId = document.getElementById('download-test-btn').dataset.testId;
  window.open(`${API_URL}/tests/${testId}/download`, '_blank');
});

// Execute Tests
document.getElementById('execute-tests-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const projectId = parseInt(document.getElementById('execute-project').value);
  const submitButton = e.target.querySelector('button[type="submit"]');
  const loadingBox = document.getElementById('execution-loading');
  const originalButtonLabel = submitButton.textContent;

  try {
    submitButton.disabled = true;
    submitButton.textContent = 'Executando...';
    loadingBox.classList.remove('hidden');
    showToast('Executando testes... Isso pode levar alguns minutos.', 'success');

    const response = await axios.post(`${API_URL}/executions/run`, {
      project_id: projectId,
      test_ids: null
    });

    const data = response.data;

    // Show results
    document.getElementById('execution-result').style.display = 'block';
    document.getElementById('stat-total').textContent = data.total_tests;
    document.getElementById('stat-passed').textContent = data.passed;
    document.getElementById('stat-failed').textContent = data.failed;
    document.getElementById('stat-skipped').textContent = data.skipped;
    const errorBox = document.getElementById('execution-error');
    if (data.error_output) {
      errorBox.textContent = data.error_output;
      errorBox.style.display = 'block';
    } else {
      errorBox.textContent = '';
      errorBox.style.display = 'none';
    }

    // Store paths for buttons
    document.getElementById('view-report-btn').dataset.reportPath = data.mkdocs_index || '';
    document.getElementById('view-robot-report-btn').dataset.reportPath = data.report_file;
    document.getElementById('view-log-btn').dataset.logPath = data.log_file;

    showToast('Testes executados com sucesso!');
  } catch (error) {
    showToast(error.response?.data?.detail || 'Erro ao executar testes', 'error');
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = originalButtonLabel;
    loadingBox.classList.add('hidden');
  }
});

// View Reports
document.getElementById('view-report-btn')?.addEventListener('click', () => {
  const reportPath = document.getElementById('view-report-btn').dataset.reportPath;
  if (reportPath) {
    window.open(reportPath, '_blank');
  }
});

document.getElementById('view-robot-report-btn')?.addEventListener('click', () => {
  const reportPath = document.getElementById('view-robot-report-btn').dataset.reportPath;
  if (reportPath) {
    window.open(reportPath, '_blank');
  }
});

document.getElementById('view-log-btn')?.addEventListener('click', () => {
  const logPath = document.getElementById('view-log-btn').dataset.logPath;
  if (logPath) {
    window.open(logPath, '_blank');
  }
});

// Load projects for execution dropdown
async function loadExecuteProjects() {
  try {
    const response = await axios.get(`${API_URL}/projects`);
    const select = document.getElementById('execute-project');
    select.innerHTML = '<option value="">Selecione um projeto...</option>';

    response.data.forEach((project) => {
      const option = document.createElement('option');
      option.value = project.id;
      option.textContent = `${project.name}${project.test_directory ? ' (' + project.test_directory + ')' : ''}`;
      select.appendChild(option);
    });
  } catch (error) {
    console.error('Error loading projects:', error);
  }
}

// Update tab navigation to load execute projects
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const tabName = btn.dataset.tab;

    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));

    btn.classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');

    if (tabName === 'projects') loadProjects();
    if (tabName === 'generate') loadProjectsDropdown();
    if (tabName === 'execute') loadExecuteProjects();
  });
});

// Initial Load
loadProjects();
