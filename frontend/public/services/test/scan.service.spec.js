import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/automaweb.api.js', () => ({
  scanProject: vi.fn()
}));

import { scanProject } from '../../api/automaweb.api.js';
import { runProjectScan } from '../scan.service.js';

beforeEach(() => vi.clearAllMocks());

describe('runProjectScan', () => {
  it('throws when URL is missing', async () => {
    await expect(runProjectScan('')).rejects.toThrow('valid project URL is required');
  });

  it('throws when URL is not http/https', async () => {
    await expect(runProjectScan('ftp://example.com')).rejects.toThrow(
      'valid project URL is required'
    );
  });

  it('throws when URL is a plain string', async () => {
    await expect(runProjectScan('not-a-url')).rejects.toThrow('valid project URL is required');
  });

  it('calls scanProject with the given URL', async () => {
    scanProject.mockResolvedValue(undefined);
    await runProjectScan('https://example.com');
    expect(scanProject).toHaveBeenCalledWith('https://example.com', expect.any(Function));
  });

  it('returns null when no result message is received', async () => {
    scanProject.mockResolvedValue(undefined);
    const result = await runProjectScan('https://example.com');
    expect(result).toBeNull();
  });

  it('returns the result data from a "result" message', async () => {
    scanProject.mockImplementation(async (_url, onMessage) => {
      onMessage({ type: 'result', data: { title: 'My Page', total_elements: 5 } });
    });
    const result = await runProjectScan('https://example.com');
    expect(result).toEqual({ title: 'My Page', total_elements: 5 });
  });

  it('calls handlers.onProgress for "progress" messages', async () => {
    scanProject.mockImplementation(async (_url, onMessage) => {
      onMessage({ type: 'progress', message: 'Scanning...' });
    });
    const onProgress = vi.fn();
    await runProjectScan('https://example.com', { onProgress });
    expect(onProgress).toHaveBeenCalledWith('Scanning...');
  });

  it('calls handlers.onResult for "result" messages', async () => {
    const data = { title: 'X', total_elements: 1 };
    scanProject.mockImplementation(async (_url, onMessage) => {
      onMessage({ type: 'result', data });
    });
    const onResult = vi.fn();
    await runProjectScan('https://example.com', { onResult });
    expect(onResult).toHaveBeenCalledWith(data);
  });

  it('calls handlers.onError for "error" messages', async () => {
    scanProject.mockImplementation(async (_url, onMessage) => {
      onMessage({ type: 'error', message: 'Timeout' });
    });
    const onError = vi.fn();
    await runProjectScan('https://example.com', { onError });
    expect(onError).toHaveBeenCalledWith('Timeout');
  });

  it('handles multiple message types in sequence', async () => {
    const data = { title: 'Z', total_elements: 3 };
    scanProject.mockImplementation(async (_url, onMessage) => {
      onMessage({ type: 'progress', message: 'step 1' });
      onMessage({ type: 'progress', message: 'step 2' });
      onMessage({ type: 'result', data });
    });
    const onProgress = vi.fn();
    const result = await runProjectScan('https://example.com', { onProgress });
    expect(onProgress).toHaveBeenCalledTimes(2);
    expect(result).toEqual(data);
  });

  it('ignores unknown message types without throwing', async () => {
    scanProject.mockImplementation(async (_url, onMessage) => {
      onMessage({ type: 'unknown', message: 'ignore me' });
    });
    await expect(runProjectScan('https://example.com')).resolves.toBeNull();
  });

  it('works without passing handlers', async () => {
    scanProject.mockImplementation(async (_url, onMessage) => {
      onMessage({ type: 'progress', message: 'x' });
      onMessage({ type: 'error', message: 'oops' });
    });
    await expect(runProjectScan('https://example.com')).resolves.toBeNull();
  });
});
