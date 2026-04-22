import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../client.js', () => ({
  request: vi.fn(),
  streamPost: vi.fn(),
}));

import {
  createProject,
  deleteGeneratedTest,
  deleteProject,
  generateRobotTest,
  generateVisualBuilderCode,
  getTestById,
  getVisualBuilderSteps,
  improveRobotTest,
  listGeneratedTests,
  listProjectExecutions,
  listProjects,
  runTests,
  saveRobotTestContent,
  scanProject,
  startVisualBuilder,
} from '../automaweb.api.js';
import { request, streamPost } from '../client.js';

beforeEach(() => vi.clearAllMocks());

describe('automaweb.api', () => {
  it('delegates listProjects to request()', async () => {
    request.mockResolvedValueOnce([]);
    await listProjects();
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/projects' });
  });

  it('delegates createProject to request()', async () => {
    const payload = { name: 'demo' };
    request.mockResolvedValueOnce({ id: 1 });
    await createProject(payload);
    expect(request).toHaveBeenCalledWith({ method: 'POST', url: '/projects', data: payload });
  });

  it('delegates deleteProject to request()', async () => {
    request.mockResolvedValueOnce(undefined);
    await deleteProject(7);
    expect(request).toHaveBeenCalledWith({ method: 'DELETE', url: '/projects/7' });
  });

  it('delegates listGeneratedTests to request()', async () => {
    request.mockResolvedValueOnce([]);
    await listGeneratedTests(3);
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/projects/3/tests' });
  });

  it('delegates deleteGeneratedTest to request()', async () => {
    request.mockResolvedValueOnce(undefined);
    await deleteGeneratedTest(99);
    expect(request).toHaveBeenCalledWith({ method: 'DELETE', url: '/tests/99' });
  });

  it('delegates generateRobotTest to request()', async () => {
    const payload = { project_id: 1, prompt: 'create login test' };
    request.mockResolvedValueOnce({ id: 11 });
    await generateRobotTest(payload);
    expect(request).toHaveBeenCalledWith({ method: 'POST', url: '/tests/generate', data: payload });
  });

  it('delegates runTests to request() with long timeout', async () => {
    const payload = { project_id: 1 };
    request.mockResolvedValueOnce({ status: 'ok' });
    await runTests(payload);
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/executions/run',
      data: payload,
      timeout: 600000,
    });
  });

  it('delegates listProjectExecutions to request()', async () => {
    request.mockResolvedValueOnce([]);
    await listProjectExecutions(5);
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/projects/5/executions' });
  });

  it('delegates scanProject to streamPost()', async () => {
    const onMessage = vi.fn();
    await scanProject('https://example.com', 5, onMessage);
    expect(streamPost).toHaveBeenCalledWith(
      '/scan',
      { url: 'https://example.com', project_id: 5 },
      onMessage
    );
  });

  it('delegates scanProject with null project_id when projectId is undefined', async () => {
    const onMessage = vi.fn();
    await scanProject('https://example.com', undefined, onMessage);
    expect(streamPost).toHaveBeenCalledWith(
      '/scan',
      { url: 'https://example.com', project_id: null },
      onMessage
    );
  });

  it('delegates improveRobotTest to request()', async () => {
    request.mockResolvedValueOnce({ content: '*** Test Cases ***' });
    await improveRobotTest(7, '*** Test Cases ***\nOld');
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/tests/7/improve',
      data: { content: '*** Test Cases ***\nOld' },
    });
  });

  it('delegates saveRobotTestContent to request()', async () => {
    request.mockResolvedValueOnce({ id: 3, content: '*** Test Cases ***' });
    await saveRobotTestContent(3, '*** Test Cases ***\nEdited');
    expect(request).toHaveBeenCalledWith({
      method: 'PUT',
      url: '/tests/3/content',
      data: { content: '*** Test Cases ***\nEdited' },
    });
  });

  it('delegates getTestById to request()', async () => {
    request.mockResolvedValueOnce({ id: 42, content: '*** Test Cases ***' });
    await getTestById(42);
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/tests/42' });
  });

  it('delegates startVisualBuilder to request()', async () => {
    request.mockResolvedValueOnce({ session_id: 'abc' });
    await startVisualBuilder('https://example.com/login');
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/builder/start',
      data: { url: 'https://example.com/login' },
    });
  });

  it('delegates getVisualBuilderSteps to request() without query', async () => {
    request.mockResolvedValueOnce({ steps: [] });
    await getVisualBuilderSteps();
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/builder/steps' });
  });

  it('delegates getVisualBuilderSteps to request() with query', async () => {
    request.mockResolvedValueOnce({ steps: [] });
    await getVisualBuilderSteps('session-123');
    expect(request).toHaveBeenCalledWith({
      method: 'GET',
      url: '/builder/steps?session_id=session-123',
    });
  });

  it('delegates generateVisualBuilderCode to request()', async () => {
    request.mockResolvedValueOnce({ code: 'await page.click()' });
    await generateVisualBuilderCode('session-123');
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/builder/generate',
      data: { session_id: 'session-123' },
    });
  });
});
