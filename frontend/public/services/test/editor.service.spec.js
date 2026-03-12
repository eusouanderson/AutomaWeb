import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/automaweb.api.js', () => ({
  improveRobotTest: vi.fn(),
  saveRobotTestContent: vi.fn(),
  listGeneratedTests: vi.fn()
}));

vi.mock('../../api/client.js', () => ({
  request: vi.fn()
}));

import {
  improveRobotTest,
  listGeneratedTests,
  saveRobotTestContent
} from '../../api/automaweb.api.js';
import { request } from '../../api/client.js';
import {
  getTestsForProject,
  improveWithAI,
  loadRobotTestContent,
  saveEditorContent
} from '../editor.service.js';

beforeEach(() => vi.clearAllMocks());

// ── loadRobotTestContent ──────────────────────────────────────────────────────

describe('loadRobotTestContent', () => {
  it('calls GET /tests/:id and returns test data', async () => {
    request.mockResolvedValue({ id: 1, content: '*** Test Cases ***', file_path: '/t.robot' });
    const result = await loadRobotTestContent(1);
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/tests/1' });
    expect(result.id).toBe(1);
  });
});

// ── getTestsForProject ────────────────────────────────────────────────────────

describe('getTestsForProject', () => {
  it('returns empty array when projectId is falsy', async () => {
    expect(await getTestsForProject(null)).toEqual([]);
    expect(await getTestsForProject(0)).toEqual([]);
    expect(listGeneratedTests).not.toHaveBeenCalled();
  });

  it('delegates to listGeneratedTests with the project id', async () => {
    listGeneratedTests.mockResolvedValue([{ id: 1, file_path: 't.robot' }]);
    const result = await getTestsForProject(3);
    expect(listGeneratedTests).toHaveBeenCalledWith(3);
    expect(result).toHaveLength(1);
  });
});

// ── improveWithAI ─────────────────────────────────────────────────────────────

describe('improveWithAI', () => {
  it('throws when testId is missing', async () => {
    await expect(improveWithAI(null, '*** Test Cases ***')).rejects.toThrow('Test id is required');
  });

  it('throws when content is empty', async () => {
    await expect(improveWithAI(1, '')).rejects.toThrow('Content must not be empty');
    await expect(improveWithAI(1, '   ')).rejects.toThrow('Content must not be empty');
  });

  it('calls improveRobotTest and returns content', async () => {
    improveRobotTest.mockResolvedValue({ content: '*** Test Cases ***\nImproved' });
    const result = await improveWithAI(5, '*** Test Cases ***\nOld Test');
    expect(improveRobotTest).toHaveBeenCalledWith(5, '*** Test Cases ***\nOld Test');
    expect(result).toBe('*** Test Cases ***\nImproved');
  });
});

// ── saveEditorContent ─────────────────────────────────────────────────────────

describe('saveEditorContent', () => {
  it('throws when testId is missing', async () => {
    await expect(saveEditorContent(0, '*** Test Cases ***')).rejects.toThrow('Test id is required');
  });

  it('throws when content is empty', async () => {
    await expect(saveEditorContent(1, '')).rejects.toThrow('Content must not be empty');
  });

  it('calls saveRobotTestContent with testId and content', async () => {
    saveRobotTestContent.mockResolvedValue({ id: 1, content: '*** Test Cases ***' });
    const result = await saveEditorContent(1, '*** Test Cases ***');
    expect(saveRobotTestContent).toHaveBeenCalledWith(1, '*** Test Cases ***');
    expect(result.id).toBe(1);
  });
});
