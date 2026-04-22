import { request, streamPost } from './client.js';

export function listProjects() {
  return request({ method: 'GET', url: '/projects' });
}

export function createProject(payload) {
  return request({ method: 'POST', url: '/projects', data: payload });
}

export function deleteProject(projectId) {
  return request({ method: 'DELETE', url: `/projects/${projectId}` });
}

export function listGeneratedTests(projectId) {
  return request({ method: 'GET', url: `/projects/${projectId}/tests` });
}

export function deleteGeneratedTest(testId) {
  return request({ method: 'DELETE', url: `/tests/${testId}` });
}

export function getTestById(testId) {
  return request({ method: 'GET', url: `/tests/${testId}` });
}

export function generateRobotTest(payload) {
  return request({ method: 'POST', url: '/tests/generate', data: payload });
}

export function runTests(payload) {
  return request({
    method: 'POST',
    url: '/executions/run',
    data: payload,
    timeout: 600000,
  });
}

export function scanProject(url, projectId, onMessage) {
  return streamPost('/scan', { url, project_id: projectId ?? null }, onMessage);
}

export function listProjectExecutions(projectId) {
  return request({ method: 'GET', url: `/projects/${projectId}/executions` });
}

export function improveRobotTest(testId, content) {
  return request({ method: 'POST', url: `/tests/${testId}/improve`, data: { content } });
}

export function saveRobotTestContent(testId, content) {
  return request({ method: 'PUT', url: `/tests/${testId}/content`, data: { content } });
}

export function startVisualBuilder(url) {
  return request({ method: 'POST', url: '/builder/start', data: { url } });
}

export function getVisualBuilderSteps(sessionId = null) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return request({ method: 'GET', url: `/builder/steps${query}` });
}

export function generateVisualBuilderCode(sessionId = null, prompt = null) {
  return request({
    method: 'POST',
    url: '/builder/generate',
    data: { session_id: sessionId, prompt },
  });
}
