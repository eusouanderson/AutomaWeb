import { toast } from '../../components/toast.js';
import {
  deleteVisualBuilderCapturedStep,
  generateTestFromPrompt,
  getAvailableAiModels,
  getProjectGeneratedTests,
  getProjects,
  getTestContent,
  getVisualBuilderCapturedSteps,
  improveExistingGeneratedTest,
  startVisualBuilderSession,
  updateVisualBuilderCapturedStep,
} from '../../services/test.service.js';
import { loadTemplate, renderHTML } from '../../utils/dom.js';

const TEMPLATE_PATH = '/static/frontend/pages/generator/generator.html';
const BUILDER_PROMPT_STORAGE = 'builder_prompt';
const BUILDER_MODEL_STORAGE = 'builder_model';
const BUILDER_PLAN_STORAGE = 'builder_plan';
const BUILDER_TEMP_STORAGE = 'builder_temperature';
const BUILDER_MAX_TOKENS_STORAGE = 'builder_max_tokens';
const BUILDER_SYSTEM_PROMPT_STORAGE = 'builder_system_prompt';

const PLAN_PRESETS = {
  balanced: {
    label: 'Balanced',
    prompt:
      'Você é um especialista em automação de testes Robot Framework. Gere cenários legíveis e estáveis com bom equilíbrio entre cobertura e simplicidade.',
  },
  strict: {
    label: 'Strict / Deterministic',
    prompt:
      'Gere testes Robot Framework determinísticos, com passos explícitos, waits necessários e validações objetivas. Evite ambiguidades.',
  },
  exploratory: {
    label: 'Exploratory',
    prompt:
      'Gere testes Robot Framework com foco em exploração funcional, cobrindo caminhos alternativos e validações relevantes mantendo robustez.',
  },
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export async function mount(root, { store }) {
  const html = await loadTemplate(TEMPLATE_PATH);
  renderHTML(root, html);
  return initGeneratorPage({ store });
}

export function initGeneratorPage({ store }) {
  const projectSelect = document.getElementById('test-project');

  const generationStatus = document.getElementById('generation-status');
  const generationStatusLabel = document.getElementById('generation-status-label');
  const generationStatusDetail = document.getElementById('generation-status-detail');
  const generationStatusTimer = document.getElementById('generation-status-timer');

  const resultSection = document.getElementById('generated-result');
  const codeElement = document.getElementById('test-code');
  const copyButton = document.getElementById('copy-test-btn');
  const downloadButton = document.getElementById('download-test-btn');

  const builderForm = document.getElementById('visual-builder-form');
  const builderUrlInput = document.getElementById('builder-url');
  const builderPromptInput = document.getElementById('builder-prompt');
  const llmModelSelect = document.getElementById('builder-llm-model');
  const llmPlanSelect = document.getElementById('builder-llm-plan');
  const llmTemperatureInput = document.getElementById('builder-llm-temperature');
  const llmMaxTokensInput = document.getElementById('builder-llm-max-tokens');
  const llmSystemPromptInput = document.getElementById('builder-llm-system-prompt');
  const llmRefreshModelsBtn = document.getElementById('builder-llm-refresh-models-btn');
  const builderStartBtn = document.getElementById('builder-start-btn');
  const builderRefreshStepsBtn = document.getElementById('builder-refresh-steps-btn');
  const builderGenerateBtn = document.getElementById('builder-generate-btn');
  const builderSessionBanner = document.getElementById('builder-session-banner');
  const builderSessionIdEl = document.getElementById('builder-session-id');
  const builderStepsPanel = document.getElementById('builder-steps-panel');
  const builderStepsSummary = document.getElementById('builder-steps-summary');
  const builderSelectedStepSummary = document.getElementById('builder-selected-step-summary');
  const builderStepsList = document.getElementById('builder-steps-list');
  const builderCodePanel = document.getElementById('builder-code-panel');
  const builderCodeEl = document.getElementById('builder-code');
  const builderCopyCodeBtn = document.getElementById('builder-copy-code-btn');

  let builderSessionId = null;
  let builderLatestSteps = [];
  let builderSelectedStepKey = null;
  let generatedBuilderStepKeys = new Set();
  let builderPollTimer = null;
  let generationTimer = null;

  if (!projectSelect) {
    return {
      loadProjectsDropdown: async () => {},
      generateFromExecutionFeedback: async () => {},
    };
  }

  if (builderPromptInput) {
    builderPromptInput.value = localStorage.getItem(BUILDER_PROMPT_STORAGE) || '';
  }
  builderPromptInput?.addEventListener('input', () => {
    localStorage.setItem(BUILDER_PROMPT_STORAGE, builderPromptInput.value);
  });

  if (llmPlanSelect) {
    llmPlanSelect.value = localStorage.getItem(BUILDER_PLAN_STORAGE) || 'balanced';
  }

  if (llmTemperatureInput) {
    llmTemperatureInput.value = localStorage.getItem(BUILDER_TEMP_STORAGE) || '0.2';
  }

  if (llmMaxTokensInput) {
    llmMaxTokensInput.value = localStorage.getItem(BUILDER_MAX_TOKENS_STORAGE) || '4096';
  }

  if (llmSystemPromptInput) {
    llmSystemPromptInput.value =
      localStorage.getItem(BUILDER_SYSTEM_PROMPT_STORAGE) ||
      PLAN_PRESETS[llmPlanSelect?.value || 'balanced'].prompt;
  }

  llmPlanSelect?.addEventListener('change', () => {
    const selectedPlan = llmPlanSelect.value || 'balanced';
    localStorage.setItem(BUILDER_PLAN_STORAGE, selectedPlan);

    const currentPrompt = (llmSystemPromptInput?.value || '').trim();
    const knownPrompts = Object.values(PLAN_PRESETS).map((preset) => preset.prompt);
    if (!currentPrompt || knownPrompts.includes(currentPrompt)) {
      if (llmSystemPromptInput) {
        llmSystemPromptInput.value = PLAN_PRESETS[selectedPlan].prompt;
      }
      localStorage.setItem(BUILDER_SYSTEM_PROMPT_STORAGE, PLAN_PRESETS[selectedPlan].prompt);
    }
  });

  llmTemperatureInput?.addEventListener('input', () => {
    localStorage.setItem(BUILDER_TEMP_STORAGE, llmTemperatureInput.value);
  });

  llmMaxTokensInput?.addEventListener('input', () => {
    localStorage.setItem(BUILDER_MAX_TOKENS_STORAGE, llmMaxTokensInput.value);
  });

  llmSystemPromptInput?.addEventListener('input', () => {
    localStorage.setItem(BUILDER_SYSTEM_PROMPT_STORAGE, llmSystemPromptInput.value);
  });

  async function loadAiModelsDropdown() {
    if (!llmModelSelect) return;

    const previousValue = localStorage.getItem(BUILDER_MODEL_STORAGE) || llmModelSelect.value || '';
    llmModelSelect.innerHTML = '<option value="">Padrão do servidor</option>';

    try {
      const response = await getAvailableAiModels();
      const models = Array.isArray(response?.models) ? response.models : [];

      models.forEach((model) => {
        const option = document.createElement('option');
        option.value = model.id;
        option.textContent = `${model.name || model.id} (${model.id})`;
        llmModelSelect.appendChild(option);
      });

      if (previousValue && models.some((model) => model.id === previousValue)) {
        llmModelSelect.value = previousValue;
      }
    } catch (error) {
      toast(error.message || 'Falha ao carregar modelos de IA', 'error');
    }
  }

  llmModelSelect?.addEventListener('change', () => {
    localStorage.setItem(BUILDER_MODEL_STORAGE, llmModelSelect.value || '');
  });

  llmRefreshModelsBtn?.addEventListener('click', async () => {
    await loadAiModelsDropdown();
    toast('Modelos de IA atualizados.');
  });

  function syncBuilderUrlWithSelectedProject() {
    if (!builderUrlInput) {
      return;
    }

    const selected = projectSelect.selectedOptions[0];
    const projectUrl = selected?.dataset?.url || '';
    builderUrlInput.value = projectUrl;
  }

  function showGenerationStatus(label = 'Gerando teste pelo Test Builder...') {
    generationStatus?.classList.remove('hidden');
    if (generationStatusLabel) generationStatusLabel.textContent = label;
    if (generationStatusDetail) {
      generationStatusDetail.textContent = 'Preparando envio para o LLM...';
    }
    if (generationStatusTimer) generationStatusTimer.textContent = '0s';

    let elapsed = 0;
    clearInterval(generationTimer);
    generationTimer = setInterval(() => {
      elapsed += 1;
      if (generationStatusTimer) generationStatusTimer.textContent = `${elapsed}s`;
      if (elapsed === 30 && generationStatusDetail) {
        generationStatusDetail.textContent = 'Aguardando resposta do LLM (pode haver fila)...';
      }
    }, 1000);
  }

  function hideGenerationStatus() {
    clearInterval(generationTimer);
    generationTimer = null;
    generationStatus?.classList.add('hidden');
  }

  function getBuilderStepKey(step, index) {
    const stepId = Number(step?.id || 0);
    if (Number.isInteger(stepId) && stepId > 0) {
      return `id:${stepId}`;
    }
    return `idx:${index}`;
  }

  function updateSelectedStepSummary(steps = []) {
    if (!builderSelectedStepSummary) {
      return;
    }

    if (!Array.isArray(steps) || steps.length === 0 || !builderSelectedStepKey) {
      builderSelectedStepSummary.textContent = '';
      builderSelectedStepSummary.classList.add('hidden');
      return;
    }

    const selectedIndex = steps.findIndex(
      (step, index) => getBuilderStepKey(step, index) === builderSelectedStepKey
    );
    if (selectedIndex < 0) {
      builderSelectedStepSummary.textContent = '';
      builderSelectedStepSummary.classList.add('hidden');
      return;
    }

    const selectedStep = steps[selectedIndex];
    const displayName =
      String(selectedStep.step_name || selectedStep.description || '').trim() ||
      `Step ${selectedStep.step || selectedIndex + 1}`;

    builderSelectedStepSummary.textContent = `Step selecionado para geracao: ${displayName}`;
    builderSelectedStepSummary.classList.remove('hidden');
  }

  function findBuilderStepByKey(stepKey, steps = builderLatestSteps) {
    if (!stepKey || !Array.isArray(steps)) {
      return null;
    }

    const index = steps.findIndex(
      (step, itemIndex) => getBuilderStepKey(step, itemIndex) === stepKey
    );
    if (index < 0) {
      return null;
    }

    return {
      step: steps[index],
      index,
    };
  }

  function getSelectedBuilderStep(steps = builderLatestSteps) {
    const selected = findBuilderStepByKey(builderSelectedStepKey, steps);
    if (selected) {
      return selected;
    }

    if (!Array.isArray(steps) || steps.length === 0) {
      return null;
    }

    builderSelectedStepKey = getBuilderStepKey(steps[0], 0);
    return {
      step: steps[0],
      index: 0,
    };
  }

  function updateBuilderGenerateButtonState(steps = builderLatestSteps) {
    if (!builderGenerateBtn) {
      return;
    }

    const selected = getSelectedBuilderStep(steps);
    if (!selected) {
      builderGenerateBtn.classList.remove('builder-generate-btn--generated');
      builderGenerateBtn.textContent = 'Gerar .robot do Step Selecionado';
      return;
    }

    const stepKey = getBuilderStepKey(selected.step, selected.index);
    const alreadyGenerated = generatedBuilderStepKeys.has(stepKey);
    builderGenerateBtn.classList.toggle('builder-generate-btn--generated', alreadyGenerated);
    builderGenerateBtn.textContent = alreadyGenerated
      ? 'Step Selecionado Ja Gerado (.robot)'
      : 'Gerar .robot do Step Selecionado';
  }

  function renderBuilderSteps(steps = []) {
    if (!builderStepsPanel || !builderStepsList || !builderStepsSummary) {
      return;
    }

    builderLatestSteps = Array.isArray(steps) ? steps : [];

    if (builderLatestSteps.length > 0) {
      const availableStepKeys = new Set(
        builderLatestSteps.map((step, index) => getBuilderStepKey(step, index))
      );
      generatedBuilderStepKeys = new Set(
        Array.from(generatedBuilderStepKeys).filter((stepKey) => availableStepKeys.has(stepKey))
      );
    } else {
      generatedBuilderStepKeys = new Set();
    }

    if (builderLatestSteps.length === 0) {
      builderSelectedStepKey = null;
      builderStepsSummary.textContent = 'Nenhum step capturado ainda.';
      builderStepsList.innerHTML = '';
      updateSelectedStepSummary([]);
      updateBuilderGenerateButtonState([]);
      builderStepsPanel.classList.remove('hidden');
      return;
    }

    const selected = getSelectedBuilderStep(builderLatestSteps);
    builderSelectedStepKey = selected ? getBuilderStepKey(selected.step, selected.index) : null;

    builderStepsSummary.textContent = `${builderLatestSteps.length} step(s) capturado(s).`;
    builderStepsList.innerHTML = builderLatestSteps
      .map((step, index) => {
        const action = String(step.action || step.type || 'unknown').toLowerCase();
        const stepId = Number(step.id || 0);
        const stepKey = getBuilderStepKey(step, index);
        const isSelected = stepKey === builderSelectedStepKey;
        const isGenerated = generatedBuilderStepKeys.has(stepKey);
        const name = String(step.step_name || '').trim();
        const description = String(step.description || step.text || '').trim();
        const metadata = [
          step.selector ? `Selector: ${step.selector}` : '',
          step.value ? `Valor: ${step.value}` : '',
          step.page_url ? `URL: ${step.page_url}` : '',
          step.page_title ? `Página: ${step.page_title}` : '',
          step.element_tag ? `Tag: ${step.element_tag}` : '',
          step.input_type ? `Tipo: ${step.input_type}` : '',
          step.href ? `Href: ${step.href}` : '',
          step.element_text ? `Texto: ${step.element_text}` : '',
          description ? `Descrição: ${description}` : '',
        ].filter(Boolean);

        return `
          <li class="builder-step-item ${isSelected ? 'is-selected' : ''}" data-step-id="${stepId || ''}" data-step-key="${escapeHtml(stepKey)}">
            <div class="builder-step-header">
              <div class="builder-step-header-main">
                <input
                  class="builder-step-select-input"
                  type="radio"
                  name="builder-selected-step"
                  data-step-key="${escapeHtml(stepKey)}"
                  ${isSelected ? 'checked' : ''}
                />
                <span class="builder-step-index">[${escapeHtml(step.step)}]</span>
                <span class="builder-step-action">${escapeHtml(action)}</span>
              </div>
              <button
                type="button"
                class="btn ${isGenerated ? 'btn-secondary builder-step-generate-btn--generated' : 'btn-primary'} builder-step-generate-btn"
                data-step-key="${escapeHtml(stepKey)}"
              >${isGenerated ? 'Teste ja gerado' : 'Gerar .robot deste step'}</button>
            </div>
            <div class="form-group">
              <label>Nome do step</label>
              <div class="builder-step-actions">
                <input
                  class="builder-step-name-input"
                  data-step-id="${stepId || ''}"
                  type="text"
                  value="${escapeHtml(name)}"
                  placeholder="Ex: Clicar no botão Entrar"
                />
                <button
                  type="button"
                  class="btn btn-secondary builder-step-save-btn"
                  data-step-id="${stepId || ''}"
                  ${stepId ? '' : 'disabled'}
                >Salvar nome</button>
                <button
                  type="button"
                  class="btn btn-danger builder-step-delete-btn"
                  data-step-id="${stepId || ''}"
                  ${stepId ? '' : 'disabled'}
                >Apagar step</button>
              </div>
            </div>
            <div class="builder-step-meta">${metadata
              .map((item) => `<div>${escapeHtml(item)}</div>`)
              .join('')}</div>
          </li>
        `;
      })
      .join('');

    updateSelectedStepSummary(builderLatestSteps);
    updateBuilderGenerateButtonState(builderLatestSteps);
    builderStepsPanel.classList.remove('hidden');
  }

  function setBuilderSession(sessionId) {
    builderSessionId = sessionId || null;
    if (builderSessionId) {
      generatedBuilderStepKeys = new Set();
      if (builderSessionIdEl) builderSessionIdEl.textContent = builderSessionId;
      builderSessionBanner?.classList.remove('hidden');
      startBuilderPoll();
    } else {
      generatedBuilderStepKeys = new Set();
      if (builderSessionIdEl) builderSessionIdEl.textContent = '-';
      builderSessionBanner?.classList.add('hidden');
      stopBuilderPoll();
    }
  }

  const startBuilderPoll = () => {
    stopBuilderPoll();
    builderPollTimer = setInterval(async () => {
      if (!builderSessionId) {
        stopBuilderPoll();
        return;
      }
      try {
        const data = await getVisualBuilderCapturedSteps(builderSessionId);
        renderBuilderSteps(data?.steps || []);
      } catch (_) {
        /* ignore transient poll failures */
      }
    }, 2500);
  };

  const stopBuilderPoll = () => {
    clearInterval(builderPollTimer);
    builderPollTimer = null;
  };

  async function refreshBuilderSteps() {
    if (!builderSessionId) {
      toast('Inicie uma sessão visual antes de buscar steps.', 'error');
      return [];
    }

    const response = await getVisualBuilderCapturedSteps(builderSessionId);
    const steps = response?.steps || [];
    renderBuilderSteps(steps);
    return steps;
  }

  async function saveBuilderStepName(stepId) {
    const input = builderStepsList?.querySelector(
      `.builder-step-name-input[data-step-id="${stepId}"]`
    );
    if (!input) {
      return;
    }

    await updateVisualBuilderCapturedStep(stepId, { step_name: input.value });
    toast('Nome do step salvo com sucesso.');
    await refreshBuilderSteps();
  }

  async function deleteBuilderStep(stepId) {
    await deleteVisualBuilderCapturedStep(stepId);
    toast('Step apagado com sucesso.');
    await refreshBuilderSteps();
  }

  function normalizeBuilderStep(step, index) {
    return {
      index: Number(step?.step || index + 1),
      action: String(step?.action || step?.type || '')
        .trim()
        .toLowerCase(),
      selector: String(step?.selector || '').trim(),
      value: step?.value == null ? '' : String(step.value),
      description: String(step?.description || step?.text || '').trim(),
      stepName: String(step?.step_name || '').trim(),
      pageUrl: String(step?.page_url || '').trim(),
      pageTitle: String(step?.page_title || '').trim(),
      elementTag: String(step?.element_tag || '').trim(),
      elementText: String(step?.element_text || '').trim(),
      inputType: String(step?.input_type || '').trim(),
      href: String(step?.href || '').trim(),
    };
  }

  function buildVisualBuilderStepContext(
    selectedStep,
    allSteps = [],
    sessionId = null,
    pageUrl = ''
  ) {
    const normalizedSelectedStep = normalizeBuilderStep(selectedStep, 0);

    const parts = [
      `- step=${normalizedSelectedStep.index}`,
      `action=${normalizedSelectedStep.action || 'unknown'}`,
      `selector=${normalizedSelectedStep.selector || 'N/A'}`,
    ];
    if (normalizedSelectedStep.value) parts.push(`value=${normalizedSelectedStep.value}`);
    if (normalizedSelectedStep.stepName) parts.push(`step_name=${normalizedSelectedStep.stepName}`);
    if (normalizedSelectedStep.description)
      parts.push(`description=${normalizedSelectedStep.description}`);
    if (normalizedSelectedStep.pageUrl) parts.push(`page_url=${normalizedSelectedStep.pageUrl}`);
    if (normalizedSelectedStep.pageTitle)
      parts.push(`page_title=${normalizedSelectedStep.pageTitle}`);
    if (normalizedSelectedStep.elementTag)
      parts.push(`element_tag=${normalizedSelectedStep.elementTag}`);
    if (normalizedSelectedStep.inputType)
      parts.push(`input_type=${normalizedSelectedStep.inputType}`);
    if (normalizedSelectedStep.href) parts.push(`href=${normalizedSelectedStep.href}`);
    if (normalizedSelectedStep.elementText)
      parts.push(`element_text=${normalizedSelectedStep.elementText}`);

    return [
      'Origem: Visual Test Builder',
      `Session ID: ${sessionId || 'N/A'}`,
      `Page URL: ${pageUrl || normalizedSelectedStep.pageUrl || 'N/A'}`,
      `Total de steps na sessao: ${Array.isArray(allSteps) ? allSteps.length : 0}`,
      '',
      'Step selecionado para geracao (envie somente este para o backend/LLM):',
      parts.join(' | '),
      '',
      'Instrucoes:',
      '- Gere UM arquivo .robot focado apenas no step selecionado.',
      '- Use seletores e metadados capturados neste step.',
      '- Gere Robot Framework valido para a Library Browser.',
      '- Retorne apenas codigo Robot Framework.',
    ].join('\n');
  }

  async function generateFromBuilderStep(step, allSteps = [], stepKey = null) {
    if (!step) {
      throw new Error('Nenhum step selecionado para geracao.');
    }

    const projectId = Number.parseInt(projectSelect.value, 10);
    if (!projectId) {
      throw new Error('Selecione um projeto antes de gerar o teste visual.');
    }

    const selectedProjectOption = projectSelect.selectedOptions[0];
    const selectedProjectUrl = selectedProjectOption?.dataset?.url || builderUrlInput?.value || '';
    const rawPrompt = builderPromptInput?.value?.trim() || '';
    const normalizedStep = normalizeBuilderStep(step, 0);
    const stepLabel =
      normalizedStep.stepName ||
      normalizedStep.description ||
      normalizedStep.selector ||
      'step selecionado';

    toast(`Gerando teste para o step: ${stepLabel}...`);

    const prompt =
      rawPrompt.length >= 5
        ? `${rawPrompt}\n\nFoque apenas no step selecionado: ${stepLabel}.`
        : `Gerar teste Robot Framework para o step selecionado: ${stepLabel}.`;

    const context = buildVisualBuilderStepContext(
      step,
      allSteps,
      builderSessionId,
      selectedProjectUrl
    );
    const model = llmModelSelect?.value?.trim() || null;
    const systemPrompt = llmSystemPromptInput?.value?.trim() || null;
    const temperature = Number.parseFloat(llmTemperatureInput?.value || '');
    const maxTokens = Number.parseInt(llmMaxTokensInput?.value || '', 10);

    showGenerationStatus('Gerando .robot do step selecionado...');
    const generated = await generateTestFromPrompt({
      projectId,
      prompt,
      context,
      ...(model ? { model } : {}),
      ...(systemPrompt ? { systemPrompt } : {}),
      ...(Number.isFinite(temperature) ? { temperature } : {}),
      ...(Number.isInteger(maxTokens) && maxTokens > 0 ? { maxTokens } : {}),
    });
    hideGenerationStatus();

    if (builderCodeEl) {
      builderCodeEl.textContent = generated?.content || '';
    }
    if (codeElement) {
      codeElement.textContent = generated?.content || '';
    }

    builderCodePanel?.classList.remove('hidden');
    resultSection?.classList.remove('hidden');
    downloadButton.dataset.testId = String(generated?.id || '');
    if (stepKey) {
      generatedBuilderStepKeys.add(stepKey);
      renderBuilderSteps(allSteps);
    }
    toast(`Arquivo .robot gerado para o step: ${stepLabel}.`);
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
              `<option value="${project.id}" data-url="${project.url || ''}">${project.name}</option>`
          )
          .join('');

      const activeId = store.getState().activeProjectId;
      if (activeId) {
        projectSelect.value = String(activeId);
      }

      syncBuilderUrlWithSelectedProject();
      if (activeId) {
        await loadBuilderStepsForProject(activeId);
      }
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function loadBuilderStepsForProject(projectId) {
    if (!projectId) {
      setBuilderSession(null);
      renderBuilderSteps([]);
      return;
    }

    const response = await getVisualBuilderCapturedSteps(null, projectId);
    setBuilderSession(response?.session_id || null);
    renderBuilderSteps(response?.steps || []);
  }

  void loadAiModelsDropdown();

  async function generateFromExecutionFeedback(projectId, feedbackText, testIds) {
    // Prefer correcting the existing file so the AI can preserve passing tests
    // and use the project directory as reference context on the backend.
    let originalContent = null;
    let targetTestId = null;

    const idsToLoad = Array.isArray(testIds) && testIds.length ? testIds : [];

    if (idsToLoad.length > 0) {
      // Load content of the first executed test (the one with errors)
      targetTestId = idsToLoad[0];
      originalContent = await getTestContent(targetTestId).catch(() => null);
    }

    if (!originalContent) {
      // Fallback: load the most recent test of the project
      const tests = await getProjectGeneratedTests(projectId).catch(() => []);
      if (tests.length > 0) {
        targetTestId = tests[0].id;
        originalContent = await getTestContent(targetTestId).catch(() => null);
      }
    }

    showGenerationStatus('Gerando correção de execução...');
    let result;
    try {
      if (targetTestId && originalContent) {
        result = await improveExistingGeneratedTest(targetTestId, originalContent, feedbackText);
      } else {
        result = await generateTestFromPrompt({
          projectId,
          prompt: 'Recriar teste com base no feedback da execucao (falhas/erros).',
          context: feedbackText,
        });
      }
    } finally {
      hideGenerationStatus();
    }

    codeElement.textContent = result.content || '';
    resultSection.classList.remove('hidden');
    downloadButton.dataset.testId = String(targetTestId || result.id || '');
    projectSelect.value = String(projectId);
    toast(
      targetTestId
        ? 'Teste existente corrigido com base nos erros da execucao!'
        : 'Teste corrigido com base nos erros da execucao!'
    );
  }

  projectSelect.addEventListener('change', async () => {
    const projectId = Number.parseInt(projectSelect.value, 10) || null;
    store.setState({ activeProjectId: projectId });
    syncBuilderUrlWithSelectedProject();
    try {
      await loadBuilderStepsForProject(projectId);
    } catch (error) {
      toast(error.message || 'Nao foi possivel carregar os steps do projeto.', 'error');
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

  builderForm?.addEventListener('submit', async (event) => {
    event.preventDefault();

    if (!projectSelect.value) {
      toast('Selecione um projeto antes de iniciar captura visual.', 'error');
      return;
    }

    const selectedProjectOption = projectSelect.selectedOptions[0];
    const selectedProjectUrl = selectedProjectOption?.dataset?.url || '';
    const url = (builderUrlInput?.value?.trim() || selectedProjectUrl).trim();

    if (!url) {
      toast('Projeto sem URL. Selecione um projeto com URL válida.', 'error');
      return;
    }

    if (builderStartBtn) builderStartBtn.disabled = true;
    try {
      const projectId = Number.parseInt(projectSelect.value, 10) || null;
      const started = await startVisualBuilderSession(url, projectId);
      setBuilderSession(started.session_id);
      renderBuilderSteps([]);
      builderCodePanel?.classList.add('hidden');
      if (builderCodeEl) builderCodeEl.textContent = '';
      toast('Builder visual iniciado. Interaja na janela do navegador aberta pelo Playwright.');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      if (builderStartBtn) builderStartBtn.disabled = false;
    }
  });

  builderRefreshStepsBtn?.addEventListener('click', async () => {
    try {
      await refreshBuilderSteps();
      toast('Steps atualizados com sucesso.');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  builderStepsList?.addEventListener('click', async (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    const saveButton = event.target.closest('.builder-step-save-btn');
    if (saveButton) {
      const stepId = Number.parseInt(saveButton.dataset.stepId || '', 10);
      if (!stepId) {
        toast('Step inválido para atualização.', 'error');
        return;
      }

      try {
        saveButton.disabled = true;
        await saveBuilderStepName(stepId);
      } catch (error) {
        toast(error.message, 'error');
      } finally {
        saveButton.disabled = false;
      }
      return;
    }

    const deleteButton = event.target.closest('.builder-step-delete-btn');
    if (deleteButton) {
      const stepId = Number.parseInt(deleteButton.dataset.stepId || '', 10);
      if (!stepId) {
        toast('Step inválido para exclusão.', 'error');
        return;
      }

      const shouldDelete =
        typeof globalThis.confirm === 'function'
          ? globalThis.confirm('Tem certeza que deseja apagar este step?')
          : true;

      if (!shouldDelete) {
        return;
      }

      try {
        deleteButton.disabled = true;
        await deleteBuilderStep(stepId);
      } catch (error) {
        toast(error.message, 'error');
      } finally {
        deleteButton.disabled = false;
      }
      return;
    }

    const generateButton = event.target.closest('.builder-step-generate-btn');
    if (generateButton) {
      const stepKey = String(generateButton.dataset.stepKey || '').trim();
      if (!stepKey) {
        toast('Step inválido para geração.', 'error');
        return;
      }

      try {
        generateButton.disabled = true;
        builderSelectedStepKey = stepKey;
        const steps = await refreshBuilderSteps();
        const selected = findBuilderStepByKey(stepKey, steps);
        if (!selected?.step) {
          toast('Step selecionado não encontrado após atualização.', 'error');
          return;
        }
        await generateFromBuilderStep(selected.step, steps, stepKey);
      } catch (error) {
        hideGenerationStatus();
        toast(error.message, 'error');
      } finally {
        generateButton.disabled = false;
      }
      return;
    }

    const stepItem = event.target.closest('.builder-step-item');
    if (stepItem) {
      const stepKey = String(stepItem.dataset.stepKey || '').trim();
      if (!stepKey) {
        return;
      }
      builderSelectedStepKey = stepKey;
      renderBuilderSteps(builderLatestSteps);
    }
  });

  builderStepsList?.addEventListener('change', (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    const input = event.target.closest('.builder-step-select-input');
    if (!input) {
      return;
    }

    const stepKey = String(input.dataset.stepKey || '').trim();
    if (!stepKey) {
      return;
    }

    builderSelectedStepKey = stepKey;
    renderBuilderSteps(builderLatestSteps);
  });

  builderStepsList?.addEventListener('keydown', async (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    const input = event.target.closest('.builder-step-name-input');
    if (!input || event.key !== 'Enter') {
      return;
    }

    event.preventDefault();
    const stepId = Number.parseInt(input.dataset.stepId || '', 10);
    if (!stepId) {
      return;
    }

    try {
      await saveBuilderStepName(stepId);
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  builderGenerateBtn?.addEventListener('click', async () => {
    if (!builderSessionId) {
      toast('Inicie uma sessão visual antes de gerar código.', 'error');
      return;
    }

    try {
      const steps = await refreshBuilderSteps();

      if (!Array.isArray(steps) || steps.length === 0) {
        toast('Nenhum step capturado. Interaja na tela antes de gerar o teste.', 'error');
        return;
      }

      const selected = getSelectedBuilderStep(steps);
      if (!selected?.step) {
        toast('Selecione um step para gerar o arquivo .robot.', 'error');
        return;
      }

      const selectedStepKey = getBuilderStepKey(selected.step, selected.index);
      await generateFromBuilderStep(selected.step, steps, selectedStepKey);
    } catch (error) {
      hideGenerationStatus();
      toast(error.message, 'error');
    }
  });

  builderCopyCodeBtn?.addEventListener('click', async () => {
    await navigator.clipboard.writeText(builderCodeEl?.textContent || '');
    toast('Código Robot copiado!');
  });

  return {
    loadProjectsDropdown,
    generateFromExecutionFeedback,
  };
}
