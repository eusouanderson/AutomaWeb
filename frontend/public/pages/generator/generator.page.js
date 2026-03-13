import { toast } from '../../components/toast.js';
import { runProjectScan } from '../../services/scan.service.js';
import {
  generateTestFromPrompt,
  getProjectGeneratedTests,
  getProjects,
  getTestContent
} from '../../services/test.service.js';
import { loadTemplate, renderHTML } from '../../utils/dom.js';

const TEMPLATE_PATH = '/static/frontend/pages/generator/generator.html';

export async function mount(root, { store }) {
  const html = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, html);
  return initGeneratorPage({ store });
}

const GEN_STORAGE_PROMPT = 'gen_prompt';
const GEN_STORAGE_CONTEXT = 'gen_context';

export function initGeneratorPage({ store }) {
  const form = document.getElementById('generate-test-form');
  const projectSelect = document.getElementById('test-project');
  const promptInput = document.getElementById('test-prompt');
  const contextInput = document.getElementById('test-context');
  const scanButton = document.getElementById('scan-page-btn');

  const scanPanel = document.getElementById('scan-panel');
  const scanSummary = document.getElementById('scan-summary');
  const scanLiveStatus = document.getElementById('scan-live-status');
  const scanReadyMessage = document.getElementById('scan-ready-message');
  const scanProgress = document.getElementById('scan-progress');
  const scanTitle = document.getElementById('scan-title');
  const scanTotal = document.getElementById('scan-total');
  const scanTypes = document.getElementById('scan-types');

  const resultSection = document.getElementById('generated-result');
  const codeElement = document.getElementById('test-code');
  const copyButton = document.getElementById('copy-test-btn');
  const downloadButton = document.getElementById('download-test-btn');
  const genScanCacheNotice = document.getElementById('gen-scan-cache-notice');
  const genScanCacheDate = document.getElementById('gen-scan-cache-date');
  const genRescanBtn = document.getElementById('gen-rescan-btn');

  let isScanning = false;
  let forceRescan = false;

  if (!form || !projectSelect) {
    return {
      loadProjectsDropdown: async () => {},
      generateFromExecutionFeedback: async () => {}
    };
  }

  // Restore saved values from localStorage
  if (promptInput) promptInput.value = localStorage.getItem(GEN_STORAGE_PROMPT) || '';
  if (contextInput) contextInput.value = localStorage.getItem(GEN_STORAGE_CONTEXT) || '';

  // Persist values on each keystroke
  promptInput?.addEventListener('input', () => {
    localStorage.setItem(GEN_STORAGE_PROMPT, promptInput.value);
  });
  contextInput?.addEventListener('input', () => {
    localStorage.setItem(GEN_STORAGE_CONTEXT, contextInput.value);
  });

  function updateCacheState() {
    const selected = projectSelect.selectedOptions[0];
    const cachedAt = selected?.dataset?.cachedAt;
    if (cachedAt) {
      if (genScanCacheDate)
        genScanCacheDate.textContent = new Date(cachedAt).toLocaleString('pt-BR');
      genScanCacheNotice?.classList.remove('hidden');
    } else {
      genScanCacheNotice?.classList.add('hidden');
    }
  }

  genRescanBtn?.addEventListener('click', () => {
    forceRescan = true;
    genRescanBtn.textContent = '↻ Scan será refeito';
    genRescanBtn.classList.add('btn-warning');
  });

  function resetScanPanel() {
    scanPanel?.classList.add('hidden');
    scanSummary?.classList.add('hidden');
    scanLiveStatus?.classList.add('hidden');
    scanReadyMessage?.classList.add('hidden');
    if (scanProgress) {
      scanProgress.innerHTML = '';
    }
    if (scanTitle) {
      scanTitle.textContent = '-';
    }
    if (scanTotal) {
      scanTotal.textContent = '0';
    }
    if (scanTypes) {
      scanTypes.textContent = '-';
    }
  }

  function appendScanProgress(message) {
    if (!scanProgress) {
      return;
    }

    const line = document.createElement('div');
    line.className = 'scan-progress-line';
    line.textContent = `• ${message}`;
    scanProgress.appendChild(line);
    scanProgress.scrollTop = scanProgress.scrollHeight;
  }

  async function loadProjectsDropdown() {
    try {
      const projects = await getProjects();
      store.setState({ projects });

      projectSelect.innerHTML =
        '<option value="">Selecione um projeto</option>' +
        projects
          .map(
            (project) =>
              `<option value="${project.id}" data-url="${project.url || ''}" data-cached-at="${project.scan_cached_at || ''}">${project.name}</option>`
          )
          .join('');
      updateCacheState();
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function generateFromExecutionFeedback(projectId, feedbackText, testIds) {
    // Load original test content so the AI can fix it instead of rewriting from scratch
    let originalContent = null;

    const idsToLoad = Array.isArray(testIds) && testIds.length ? testIds : [];

    if (idsToLoad.length > 0) {
      // Load content of the first executed test (the one with errors)
      originalContent = await getTestContent(idsToLoad[0]).catch(() => null);
    }

    if (!originalContent) {
      // Fallback: load the most recent test of the project
      const tests = await getProjectGeneratedTests(projectId).catch(() => []);
      if (tests.length > 0) {
        originalContent = await getTestContent(tests[0].id).catch(() => null);
      }
    }

    const prompt = originalContent
      ? 'Corrija os test cases com falha no arquivo Robot Framework abaixo. Mantenha TODOS os test cases que passaram exatamente como estao. Retorne o arquivo completo e corrigido.'
      : 'Recriar teste com base no feedback da execucao (falhas/erros).';

    const context = originalContent
      ? `${feedbackText}\n\n--- CODIGO ROBOT FRAMEWORK ORIGINAL ---\n${originalContent}`
      : feedbackText;

    const result = await generateTestFromPrompt({ projectId, prompt, context });

    codeElement.textContent = result.content || '';
    resultSection.classList.remove('hidden');
    downloadButton.dataset.testId = String(result.id || '');
    projectSelect.value = String(projectId);
    promptInput.value = prompt;
    contextInput.value = context;
    toast('Teste corrigido com base nos erros da execucao!');
  }

  scanButton?.addEventListener('click', async () => {
    if (isScanning) {
      return;
    }

    const projectId = Number.parseInt(projectSelect.value, 10);
    const selectedOption = projectSelect.options[projectSelect.selectedIndex];
    const projectUrl = selectedOption?.dataset?.url;

    if (!projectId) {
      toast('Selecione um projeto antes de escanear.', 'error');
      return;
    }

    if (!projectUrl) {
      toast('Projeto sem URL. Edite/crie um projeto com URL válida.', 'error');
      return;
    }

    resetScanPanel();
    scanPanel?.classList.remove('hidden');
    scanLiveStatus?.classList.remove('hidden');
    scanReadyMessage?.classList.add('hidden');
    scanButton.disabled = true;
    isScanning = true;
    appendScanProgress('Iniciando escaneamento...');

    try {
      const result = await runProjectScan(projectUrl, projectId, {
        onProgress: (message) => appendScanProgress(message),
        onError: (message) => {
          appendScanProgress(`Erro: ${message}`);
          toast(message || 'Erro no scan', 'error');
        }
      });

      if (result) {
        store.setState({
          lastScanResult: result,
          activeProjectId: projectId
        });

        scanSummary?.classList.remove('hidden');
        if (scanTitle) {
          scanTitle.textContent = result.title || '-';
        }
        if (scanTotal) {
          scanTotal.textContent = String(result.total_elements || 0);
        }
        if (scanTypes) {
          scanTypes.textContent =
            Object.entries(result.summary || {})
              .map(([key, count]) => `${key}: ${count}`)
              .join(', ') || '-';
        }

        scanReadyMessage?.classList.remove('hidden');
        appendScanProgress('Dados estruturados prontos para geração de teste.');
        toast('Scan concluído com sucesso!');

        // Update cache notice with the new scan date
        const selectedOption = projectSelect.options[projectSelect.selectedIndex];
        const now = new Date().toISOString();
        if (selectedOption) selectedOption.dataset.cachedAt = now;
        forceRescan = false;
        if (genRescanBtn) {
          genRescanBtn.textContent = '↻ Refazer scan';
          genRescanBtn.classList.remove('btn-warning');
        }
        updateCacheState();
      }
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      isScanning = false;
      scanLiveStatus?.classList.add('hidden');
      scanButton.disabled = false;
    }
  });

  projectSelect.addEventListener('change', () => {
    resetScanPanel();
    forceRescan = false;
    if (genRescanBtn) {
      genRescanBtn.textContent = '↻ Refazer scan';
      genRescanBtn.classList.remove('btn-warning');
    }
    updateCacheState();
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const projectId = Number.parseInt(projectSelect.value, 10);
    const prompt = promptInput.value;
    const context = contextInput.value;

    resultSection.classList.add('hidden');

    const state = store.getState();
    const selectedOption = projectSelect.options[projectSelect.selectedIndex];
    const hasCachedScan = !!selectedOption?.dataset?.cachedAt;
    const hasFreshScan = state.lastScanResult && state.activeProjectId === projectId;

    if (!hasFreshScan && !hasCachedScan) {
      toast('Execute o scan da página antes de gerar o teste.', 'error');
      return;
    }

    try {
      toast('Gerando teste... Aguarde.', 'info');
      const result = await generateTestFromPrompt({ projectId, prompt, context, forceRescan });
      codeElement.textContent = result.content || '';
      resultSection.classList.remove('hidden');
      downloadButton.dataset.testId = String(result.id || '');
      toast('Teste gerado com sucesso!');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  copyButton?.addEventListener('click', async () => {
    await navigator.clipboard.writeText(codeElement.textContent || '');
    toast('Código copiado!');
  });

  downloadButton?.addEventListener('click', () => {
    const testId = downloadButton.dataset.testId;
    if (!testId) {
      return;
    }
    globalThis.open(`/tests/${testId}/download`, '_blank');
  });

  return {
    loadProjectsDropdown,
    generateFromExecutionFeedback
  };
}
