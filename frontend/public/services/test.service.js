import {
  createProject,
  deleteGeneratedTest,
  deleteProject,
  generateRobotTest,
  listGeneratedTests,
  listProjects,
  runTests
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

export async function generateTestFromPrompt({ projectId, prompt, context }) {
  if (!projectId) {
    throw new Error('Project is required');
  }
  if (!requiredText(prompt, 5)) {
    throw new Error('Prompt must have at least 5 chars');
  }

  return generateRobotTest({
    project_id: projectId,
    prompt,
    context: context?.trim() || null
  });
}

export async function executeProjectTests(projectId, testIds = null, headless = true) {
  if (!projectId) {
    throw new Error('Project is required for execution');
  }

  return runTests({
    project_id: projectId,
    test_ids: testIds?.length ? testIds : null,
    headless
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
