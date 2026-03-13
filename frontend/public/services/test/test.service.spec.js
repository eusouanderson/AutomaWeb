import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/automaweb.api.js', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  deleteProject: vi.fn(),
  generateRobotTest: vi.fn(),
  runTests: vi.fn(),
  listGeneratedTests: vi.fn(),
  deleteGeneratedTest: vi.fn(),
  getTestById: vi.fn(),
  listProjectExecutions: vi.fn()
}));

import {
  createProject,
  deleteGeneratedTest,
  deleteProject,
  generateRobotTest,
  getTestById,
  listGeneratedTests,
  listProjectExecutions,
  listProjects,
  runTests
} from '../../api/automaweb.api.js';

import {
  createProjectService,
  deleteGeneratedTestService,
  deleteProjectService,
  executeProjectTests,
  generateTestFromPrompt,
  getProjectExecutions,
  getProjectGeneratedTests,
  getProjects,
  getTestContent
} from '../test.service.js';

beforeEach(() => vi.clearAllMocks());

// ── getProjects ───────────────────────────────────────────────────────────────

describe('getProjects', () => {
  it('delegates to listProjects()', async () => {
    listProjects.mockResolvedValue([{ id: 1 }]);
    await getProjects();
    expect(listProjects).toHaveBeenCalledTimes(1);
  });

  it('returns the project list', async () => {
    listProjects.mockResolvedValue([{ id: 2, name: 'X' }]);
    expect(await getProjects()).toEqual([{ id: 2, name: 'X' }]);
  });
});

// ── createProjectService ──────────────────────────────────────────────────────

describe('createProjectService', () => {
  const valid = { name: 'My Project', test_directory: 'tests/', url: 'https://example.com' };

  it('delegates to createProject with valid payload', async () => {
    createProject.mockResolvedValue({ id: 10 });
    await createProjectService(valid);
    expect(createProject).toHaveBeenCalledWith(valid);
  });

  it('throws when name is too short', async () => {
    await expect(createProjectService({ ...valid, name: 'X' })).rejects.toThrow('at least 2 chars');
  });

  it('throws when test_directory is missing', async () => {
    await expect(createProjectService({ ...valid, test_directory: 'x' })).rejects.toThrow(
      'Test directory is required'
    );
  });

  it('throws when URL is invalid', async () => {
    await expect(createProjectService({ ...valid, url: 'not-a-url' })).rejects.toThrow(
      'Project URL must be valid'
    );
  });
});

// ── deleteProjectService ──────────────────────────────────────────────────────

describe('deleteProjectService', () => {
  it('delegates to deleteProject with the given id', async () => {
    deleteProject.mockResolvedValue(undefined);
    await deleteProjectService(7);
    expect(deleteProject).toHaveBeenCalledWith(7);
  });
});

// ── generateTestFromPrompt ────────────────────────────────────────────────────

describe('generateTestFromPrompt', () => {
  const valid = { projectId: 1, prompt: 'Login flow test', context: '  some ctx  ' };

  it('delegates to generateRobotTest with correct payload', async () => {
    generateRobotTest.mockResolvedValue({ id: 5 });
    await generateTestFromPrompt(valid);
    expect(generateRobotTest).toHaveBeenCalledWith({
      project_id: 1,
      prompt: 'Login flow test',
      context: 'some ctx',
      force_rescan: false
    });
  });

  it('sends null context when context is empty', async () => {
    generateRobotTest.mockResolvedValue({ id: 6 });
    await generateTestFromPrompt({ projectId: 1, prompt: 'Login test', context: '   ' });
    expect(generateRobotTest).toHaveBeenCalledWith(expect.objectContaining({ context: null }));
  });

  it('sends null context when context is undefined', async () => {
    generateRobotTest.mockResolvedValue({ id: 7 });
    await generateTestFromPrompt({ projectId: 1, prompt: 'Login test' });
    expect(generateRobotTest).toHaveBeenCalledWith(expect.objectContaining({ context: null }));
  });

  it('throws when projectId is missing', async () => {
    await expect(generateTestFromPrompt({ prompt: 'Login test' })).rejects.toThrow(
      'Project is required'
    );
  });

  it('throws when prompt is too short', async () => {
    await expect(generateTestFromPrompt({ projectId: 1, prompt: 'abc' })).rejects.toThrow(
      'at least 5 chars'
    );
  });
});

// ── executeProjectTests ───────────────────────────────────────────────────────

describe('executeProjectTests', () => {
  it('delegates to runTests with project_id and headless', async () => {
    runTests.mockResolvedValue({ status: 'ok' });
    await executeProjectTests(3);
    expect(runTests).toHaveBeenCalledWith({
      project_id: 3,
      test_ids: null,
      headless: true
    });
  });

  it('passes test_ids when provided', async () => {
    runTests.mockResolvedValue({ status: 'ok' });
    await executeProjectTests(3, [1, 2]);
    expect(runTests).toHaveBeenCalledWith({ project_id: 3, test_ids: [1, 2], headless: true });
  });

  it('sends null test_ids for an empty array', async () => {
    runTests.mockResolvedValue({ status: 'ok' });
    await executeProjectTests(3, []);
    expect(runTests).toHaveBeenCalledWith(expect.objectContaining({ test_ids: null }));
  });

  it('respects headless=false', async () => {
    runTests.mockResolvedValue({ status: 'ok' });
    await executeProjectTests(3, null, false);
    expect(runTests).toHaveBeenCalledWith(expect.objectContaining({ headless: false }));
  });

  it('throws when projectId is falsy', async () => {
    await expect(executeProjectTests(0)).rejects.toThrow('Project is required for execution');
  });
});

// ── getProjectGeneratedTests ──────────────────────────────────────────────────

describe('getProjectGeneratedTests', () => {
  it('returns empty array when projectId is falsy', async () => {
    expect(await getProjectGeneratedTests(0)).toEqual([]);
    expect(listGeneratedTests).not.toHaveBeenCalled();
  });

  it('delegates to listGeneratedTests with valid projectId', async () => {
    listGeneratedTests.mockResolvedValue([{ id: 1 }]);
    await getProjectGeneratedTests(4);
    expect(listGeneratedTests).toHaveBeenCalledWith(4);
  });
});

// ── deleteGeneratedTestService ────────────────────────────────────────────────

describe('deleteGeneratedTestService', () => {
  it('delegates to deleteGeneratedTest with the given testId', async () => {
    deleteGeneratedTest.mockResolvedValue(undefined);
    await deleteGeneratedTestService(99);
    expect(deleteGeneratedTest).toHaveBeenCalledWith(99);
  });

  it('throws when testId is falsy', async () => {
    await expect(deleteGeneratedTestService(0)).rejects.toThrow('Test id is required');
  });
});

// ── getProjectExecutions ──────────────────────────────────────────────────────

describe('getProjectExecutions', () => {
  it('returns empty array when projectId is falsy', async () => {
    expect(await getProjectExecutions(0)).toEqual([]);
    expect(listProjectExecutions).not.toHaveBeenCalled();
  });

  it('delegates to listProjectExecutions with valid projectId', async () => {
    listProjectExecutions.mockResolvedValue([{ id: 1 }]);
    await getProjectExecutions(5);
    expect(listProjectExecutions).toHaveBeenCalledWith(5);
  });
});

// ── getTestContent ────────────────────────────────────────────────────────────

describe('getTestContent', () => {
  it('returns null when testId is falsy', async () => {
    expect(await getTestContent(0)).toBeNull();
    expect(getTestById).not.toHaveBeenCalled();
  });

  it('returns content when getTestById resolves with content', async () => {
    getTestById.mockResolvedValue({ id: 5, content: '*** Test Cases ***\nLogin\n    Log  ok' });
    const result = await getTestContent(5);
    expect(getTestById).toHaveBeenCalledWith(5);
    expect(result).toBe('*** Test Cases ***\nLogin\n    Log  ok');
  });

  it('returns null when getTestById resolves with no content', async () => {
    getTestById.mockResolvedValue({ id: 6, content: null });
    expect(await getTestContent(6)).toBeNull();
  });
});
