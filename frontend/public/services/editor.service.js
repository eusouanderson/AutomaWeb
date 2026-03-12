import {
  improveRobotTest,
  listGeneratedTests,
  saveRobotTestContent
} from '../api/automaweb.api.js';

/**
 * Load a generated test by fetching the project's test list and finding the one with the given id.
 * The full content is returned from the `/tests/{test_id}` endpoint via GET.
 */
export async function loadRobotTestContent(testId) {
  const { request } = await import('../api/client.js');
  const test = await request({ method: 'GET', url: `/tests/${testId}` });
  return test;
}

/**
 * Fetch all generated tests for a project and return a list suitable for a dropdown.
 */
export async function getTestsForProject(projectId) {
  if (!projectId) return [];
  return listGeneratedTests(projectId);
}

/**
 * Send current editor content to the AI for improvement.
 * Returns the improved Robot Framework content string.
 */
export async function improveWithAI(testId, content) {
  if (!testId) throw new Error('Test id is required');
  if (!content || !content.trim()) throw new Error('Content must not be empty');
  const result = await improveRobotTest(testId, content);
  return result.content;
}

/**
 * Persist the current editor content back to disk and DB.
 * Returns the updated generated test record.
 */
export async function saveEditorContent(testId, content) {
  if (!testId) throw new Error('Test id is required');
  if (!content || !content.trim()) throw new Error('Content must not be empty');
  return saveRobotTestContent(testId, content);
}
