import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/client.js', () => ({ request: vi.fn() }));

import { request } from '../../api/client.js';
import {
  copilotHealthCheck,
  copilotStorage,
  generateContent,
  generateRobotTestWithCopilot,
  isCopilotAuthenticated,
  listCopilotModels,
  pollCopilotAuth,
  startCopilotAuth,
} from '../copilot.service.js';

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// requestWithRetry (tested indirectly via exported functions)
// ---------------------------------------------------------------------------

describe('requestWithRetry', () => {
  it('returns on first successful attempt', async () => {
    request.mockResolvedValueOnce({ models: ['m1'] });
    const result = await listCopilotModels();
    expect(result).toEqual(['m1']);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('retries on failure and succeeds on second attempt', async () => {
    vi.useFakeTimers();
    const err = new Error('network');
    request.mockRejectedValueOnce(err).mockResolvedValueOnce({ models: ['m2'] });

    const promise = listCopilotModels();
    // advance past first retry delay (1000 * 2^0 = 1000 ms)
    await vi.advanceTimersByTimeAsync(1000);
    const result = await promise;
    expect(result).toEqual(['m2']);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('retries up to MAX_RETRIES and throws after exhausting', async () => {
    vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn) => {
      fn();
      return 0;
    });
    const err = new Error('persistent');
    request.mockRejectedValueOnce(err).mockRejectedValueOnce(err).mockRejectedValueOnce(err);
    await expect(listCopilotModels()).rejects.toThrow('persistent');
    expect(request).toHaveBeenCalledTimes(3);
  });
});

// ---------------------------------------------------------------------------
// startCopilotAuth
// ---------------------------------------------------------------------------

describe('startCopilotAuth', () => {
  it('calls POST /api/ai/authorize with null enterprise_url by default', async () => {
    request.mockResolvedValueOnce({ device_code: 'abc' });
    const result = await startCopilotAuth();
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/ai/authorize',
      data: { enterprise_url: null },
    });
    expect(result).toEqual({ device_code: 'abc' });
  });

  it('passes enterprise_url when provided', async () => {
    request.mockResolvedValueOnce({ device_code: 'xyz' });
    await startCopilotAuth('https://github.example.com');
    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({ data: { enterprise_url: 'https://github.example.com' } })
    );
  });
});

// ---------------------------------------------------------------------------
// isCopilotAuthenticated
// ---------------------------------------------------------------------------

describe('isCopilotAuthenticated', () => {
  it('returns true when authenticated === true', async () => {
    request.mockResolvedValueOnce({ authenticated: true });
    expect(await isCopilotAuthenticated()).toBe(true);
  });

  it('returns false when authenticated !== true', async () => {
    request.mockResolvedValueOnce({ authenticated: false });
    expect(await isCopilotAuthenticated()).toBe(false);
  });

  it('returns false when request throws', async () => {
    request.mockRejectedValueOnce(new Error('fail'));
    expect(await isCopilotAuthenticated()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// pollCopilotAuth
// ---------------------------------------------------------------------------

describe('pollCopilotAuth', () => {
  it('returns true immediately when already authenticated', async () => {
    vi.useFakeTimers();
    request.mockResolvedValue({ authenticated: true });
    const promise = pollCopilotAuth(5, 500);
    await vi.runAllTimersAsync();
    expect(await promise).toBe(true);
  });

  it('returns true after a few polling attempts', async () => {
    vi.useFakeTimers();
    request
      .mockResolvedValueOnce({ authenticated: false })
      .mockResolvedValueOnce({ authenticated: false })
      .mockResolvedValueOnce({ authenticated: true });

    const promise = pollCopilotAuth(5, 100);
    await vi.runAllTimersAsync();
    expect(await promise).toBe(true);
  });

  it('returns false after exhausting maxAttempts', async () => {
    vi.useFakeTimers();
    request.mockResolvedValue({ authenticated: false });

    const promise = pollCopilotAuth(3, 100);
    await vi.runAllTimersAsync();
    expect(await promise).toBe(false);
    // 3 checks total
    expect(request).toHaveBeenCalledTimes(3);
  });
});

// ---------------------------------------------------------------------------
// listCopilotModels
// ---------------------------------------------------------------------------

describe('listCopilotModels', () => {
  it('returns models array from response', async () => {
    request.mockResolvedValueOnce({ models: ['gpt-4o', 'gpt-3.5-turbo'] });
    const models = await listCopilotModels();
    expect(models).toEqual(['gpt-4o', 'gpt-3.5-turbo']);
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/api/ai/models' });
  });
});

// ---------------------------------------------------------------------------
// generateContent
// ---------------------------------------------------------------------------

describe('generateContent', () => {
  it('calls POST /api/ai/generate with prompt', async () => {
    request.mockResolvedValueOnce({ content: 'result' });
    const result = await generateContent('my prompt');
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/ai/generate',
      data: { prompt: 'my prompt' },
    });
    expect(result).toEqual({ content: 'result' });
  });

  it('merges options into data', async () => {
    request.mockResolvedValueOnce({ content: 'ok' });
    await generateContent('p', { model: 'gpt-4o', temperature: 0.5 });
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/ai/generate',
      data: { prompt: 'p', model: 'gpt-4o', temperature: 0.5 },
    });
  });
});

// ---------------------------------------------------------------------------
// generateRobotTestWithCopilot
// ---------------------------------------------------------------------------

describe('generateRobotTestWithCopilot', () => {
  it('calls POST /api/ai/robot-test with prompt', async () => {
    request.mockResolvedValueOnce({ test: '*** Test Cases ***' });
    const result = await generateRobotTestWithCopilot('describe login');
    expect(request).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/ai/robot-test',
      data: { prompt: 'describe login' },
    });
    expect(result).toEqual({ test: '*** Test Cases ***' });
  });

  it('merges options into data', async () => {
    request.mockResolvedValueOnce({ test: 'ok' });
    await generateRobotTestWithCopilot('p', { model: 'gpt-4o' });
    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({ data: { prompt: 'p', model: 'gpt-4o' } })
    );
  });
});

// ---------------------------------------------------------------------------
// copilotHealthCheck
// ---------------------------------------------------------------------------

describe('copilotHealthCheck', () => {
  it('returns health response on success', async () => {
    request.mockResolvedValueOnce({ ok: true, authenticated: true });
    const result = await copilotHealthCheck();
    expect(result).toEqual({ ok: true, authenticated: true });
    expect(request).toHaveBeenCalledWith({ method: 'GET', url: '/api/ai/health' });
  });

  it('returns error object when request throws', async () => {
    const err = new Error('network error');
    request.mockRejectedValueOnce(err);
    const result = await copilotHealthCheck();
    expect(result).toEqual({
      ok: false,
      authenticated: false,
      message: String(err),
    });
  });
});

// ---------------------------------------------------------------------------
// copilotStorage
// ---------------------------------------------------------------------------

describe('copilotStorage', () => {
  it('getModel returns default when nothing stored', () => {
    expect(copilotStorage.getModel()).toBe('gpt-4o-mini');
  });

  it('setModel and getModel round-trip', () => {
    copilotStorage.setModel('gpt-4o');
    expect(copilotStorage.getModel()).toBe('gpt-4o');
  });

  it('getLastPrompt returns empty string when nothing stored', () => {
    expect(copilotStorage.getLastPrompt()).toBe('');
  });

  it('setLastPrompt and getLastPrompt round-trip', () => {
    copilotStorage.setLastPrompt('hello world');
    expect(copilotStorage.getLastPrompt()).toBe('hello world');
  });

  it('getAuthToken returns null when nothing stored', () => {
    expect(copilotStorage.getAuthToken()).toBeNull();
  });

  it('setAuthToken and getAuthToken round-trip', () => {
    copilotStorage.setAuthToken('tok123');
    expect(copilotStorage.getAuthToken()).toBe('tok123');
  });

  it('clearAuth removes the token', () => {
    copilotStorage.setAuthToken('tok123');
    copilotStorage.clearAuth();
    expect(copilotStorage.getAuthToken()).toBeNull();
  });
});
