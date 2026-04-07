import { toast } from '../../components/toast.js';
import { runProjectScan } from '../../services/scan.service.js';
import {
  generateTestFromPrompt,
  getProjectGeneratedTests,
  getProjects,
  getTestContent,
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

  const submitBtn = document.getElementById('generate-submit-btn');
  const generationStatus = document.getElementById('generation-status');
  const generationStatusLabel = document.getElementById('generation-status-label');
  const generationStatusDetail = document.getElementById('generation-status-detail');
  const generationStatusTimer = document.getElementById('generation-status-timer');

  const resultSection = document.getElementById('generated-result');
  const generationParts = document.getElementById('generation-parts');
  const generationPartsSummary = document.getElementById('generation-parts-summary');
  const generationPartsList = document.getElementById('generation-parts-list');
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
      generateFromExecutionFeedback: async () => {},
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

  let _generationTimerInterval = null;

  function showGenerationStatus(estimatedChunks) {
    generationStatus?.classList.remove('hidden');
    if (generationStatusLabel) generationStatusLabel.textContent = 'Gerando teste...';
    if (generationStatusDetail) {
      generationStatusDetail.textContent =
        estimatedChunks > 1
          ? `Estimativa: ${estimatedChunks} parte(s) a enviar para o LLM`
          : 'Preparando envio para o LLM...';
    }
    if (generationStatusTimer) generationStatusTimer.textContent = '0s';
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Gerando...';
    }
    let elapsed = 0;
    clearInterval(_generationTimerInterval);
    _generationTimerInterval = setInterval(() => {
      elapsed += 1;
      if (generationStatusTimer) generationStatusTimer.textContent = `${elapsed}s`;
      if (elapsed === 30 && generationStatusDetail) {
        generationStatusDetail.textContent = 'Aguardando resposta do LLM (pode haver fila)...';
      }
    }, 1000);
  }

  function hideGenerationStatus() {
    clearInterval(_generationTimerInterval);
    _generationTimerInterval = null;
    generationStatus?.classList.add('hidden');
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Gerar Teste';
    }
  }

  function estimateChunks(totalElements) {
    // ~250 chars/element, chunk target ~12 000 chars → ~48 elements/chunk
    if (!totalElements) return 1;
    return Math.max(1, Math.ceil(totalElements / 48));
  }

  function resetGenerationParts() {
    generationParts?.classList.add('hidden');
    if (generationPartsSummary) {
      generationPartsSummary.textContent = '';
    }
    if (generationPartsList) {
      generationPartsList.innerHTML = '';
    }
  }

  function renderGenerationParts(result) {
    const strategy = result?.generation_strategy;
    const chunkCount = Number(result?.chunk_count || 0);
    const chunkParts = Array.isArray(result?.chunk_parts) ? result.chunk_parts : [];

    if (strategy !== 'chunked' || chunkCount <= 0) {
      resetGenerationParts();
      return;
    }

    if (generationPartsSummary) {
      generationPartsSummary.textContent =
        `Gerado em ${chunkCount} parte(s) do scan e consolidado em 1 arquivo .robot.` +
        (result?.chunk_target_chars
          ? ` (alvo por parte: ~${result.chunk_target_chars} caracteres)`
          : '');
    }

    if (generationPartsList) {
      generationPartsList.innerHTML = chunkParts
        .map((part) => {
          const keys = Array.isArray(part.keys) && part.keys.length ? part.keys.join(', ') : '-';
          return `<li>Parte ${part.index}: ~${part.approx_chars || 0} chars | chaves: ${keys}</li>`;
        })
        .join('');
    }

    generationParts?.classList.remove('hidden');
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

      const activeId = store.getState().activeProjectId;
      if (activeId) {
        projectSelect.value = String(activeId);
      }

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

    showGenerationStatus(1);
    let result;
    try {
      result = await generateTestFromPrompt({ projectId, prompt, context });
    } finally {
      hideGenerationStatus();
    }

    codeElement.textContent = result.content || '';
    renderGenerationParts(result);
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
        },
      });

      if (result) {
        store.setState({
          lastScanResult: result,
          activeProjectId: projectId,
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
    const projectId = Number.parseInt(projectSelect.value, 10) || null;
    store.setState({ activeProjectId: projectId });
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
    resetGenerationParts();

    const state = store.getState();
    const selectedOption = projectSelect.options[projectSelect.selectedIndex];
    const hasCachedScan = !!selectedOption?.dataset?.cachedAt;
    const hasFreshScan = state.lastScanResult && state.activeProjectId === projectId;
    const totalElements = Number(state.lastScanResult?.total_elements || 0);

    if (!hasFreshScan && !hasCachedScan) {
      toast('Execute o scan da página antes de gerar o teste.', 'error');
      return;
    }

    try {
      showGenerationStatus(estimateChunks(totalElements));
      const result = await generateTestFromPrompt({ projectId, prompt, context, forceRescan });
      hideGenerationStatus();
      codeElement.textContent = result.content || '';
      renderGenerationParts(result);
      resultSection.classList.remove('hidden');
      downloadButton.dataset.testId = String(result.id || '');
      toast('Teste gerado com sucesso!');
    } catch (error) {
      hideGenerationStatus();
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
    generateFromExecutionFeedback,
  };
}
