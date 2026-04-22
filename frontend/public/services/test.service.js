import {
  createProject,
  deleteGeneratedTest,
  deleteProject,
  generateRobotTest,
  generateVisualBuilderCode,
  getTestById,
  getVisualBuilderSteps,
  listGeneratedTests,
  listProjectExecutions,
  listProjects,
  runTests,
  startVisualBuilder,
} from '../api/automaweb.api.js';
import { isValidUrl, requiredText } from '../utils/validators.js';

export async function getProjects() {
  return listProjects();
}

export async function createProjectService(payload) {
  if (!requiredText(payload.name, 2)) {
    throw new Error('Project name must have at least 2 chars');
  }
  if (!requiredText(payload.test_directory, 2)) {
    throw new Error('Test directory is required');
  }
  if (!isValidUrl(payload.url)) {
    throw new Error('Project URL must be valid');
  }

  return createProject(payload);
}

export async function deleteProjectService(projectId) {
  return deleteProject(projectId);
}

export async function generateTestFromPrompt({ projectId, prompt, context, forceRescan = false }) {
  if (!projectId) {
    throw new Error('Project is required');
  }
  if (!requiredText(prompt, 5)) {
    throw new Error('Prompt must have at least 5 chars');
  }

  return generateRobotTest({
    project_id: projectId,
    prompt,
    context: context?.trim() || null,
    force_rescan: forceRescan,
  });
}

export async function executeProjectTests(projectId, testIds = null, options = {}) {
  if (!projectId) {
    throw new Error('Project is required for execution');
  }

  const normalizedOptions = typeof options === 'boolean' ? { headless: options } : options || {};

  const headless = normalizedOptions.headless ?? true;
  const timeoutSeconds = Number.isFinite(Number(normalizedOptions.timeoutSeconds))
    ? Math.min(3600, Math.max(30, Number(normalizedOptions.timeoutSeconds)))
    : 300;
  const speedMs = Number.isFinite(Number(normalizedOptions.speedMs))
    ? Math.min(10000, Math.max(0, Number(normalizedOptions.speedMs)))
    : 0;

  return runTests({
    project_id: projectId,
    test_ids: testIds?.length ? testIds : null,
    headless,
    timeout_seconds: timeoutSeconds,
    speed_ms: speedMs,
  });
}

export async function getProjectGeneratedTests(projectId) {
  if (!projectId) {
    return [];
  }
  return listGeneratedTests(projectId);
}

export async function deleteGeneratedTestService(testId) {
  if (!testId) {
    throw new Error('Test id is required');
  }

  return deleteGeneratedTest(testId);
}

export async function getTestContent(testId) {
  if (!testId) return null;
  const test = await getTestById(testId);
  return test?.content ?? null;
}

export async function getProjectExecutions(projectId) {
  if (!projectId) {
    return [];
  }
  return listProjectExecutions(projectId);
}

export async function startVisualBuilderSession(url) {
  if (!isValidUrl(url)) {
    throw new Error('Builder URL must be valid');
  }
  return startVisualBuilder(url);
}

export async function getVisualBuilderCapturedSteps(sessionId) {
  return getVisualBuilderSteps(sessionId || null);
}

export async function generateVisualBuilderPlaywrightCode(sessionId, prompt = null) {
  return generateVisualBuilderCode(sessionId || null, prompt || null);
}
