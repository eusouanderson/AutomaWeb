import { describe, expect, it, vi } from 'vitest';

vi.mock('../api/client.js', () => ({
  request: vi.fn(),
  streamPost: vi.fn()
}));

import {
  createProject,
  generateRobotTest,
  listProjects,
  scanProject
} from '../api/automaweb.api.js';
import { request, streamPost } from '../api/client.js';

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

  it('delegates generateRobotTest to request()', async () => {
    const payload = { project_id: 1, prompt: 'create login test' };
    request.mockResolvedValueOnce({ id: 11 });
    await generateRobotTest(payload);
    expect(request).toHaveBeenCalledWith({ method: 'POST', url: '/tests/generate', data: payload });
  });

  it('delegates scanProject to streamPost()', async () => {
    const onMessage = vi.fn();
    await scanProject('https://example.com', onMessage);
    expect(streamPost).toHaveBeenCalledWith('/scan', { url: 'https://example.com' }, onMessage);
  });
});
