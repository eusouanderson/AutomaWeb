import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('client.js', () => {
  let request;
  let streamPost;
  let mockHttp;
  let capturedSuccessInterceptor;
  let capturedErrorInterceptor;

  beforeEach(async () => {
    vi.resetModules();
    capturedSuccessInterceptor = null;
    capturedErrorInterceptor = null;

    mockHttp = {
      request: vi.fn(),
      interceptors: {
        response: {
          use: vi.fn((ok, err) => {
            capturedSuccessInterceptor = ok;
            capturedErrorInterceptor = err;
          })
        }
      }
    };

    vi.stubGlobal('axios', { create: vi.fn().mockReturnValue(mockHttp) });

    const mod = await import('../client.js');
    request = mod.request;
    streamPost = mod.streamPost;
  });

  // ── request ──────────────────────────────────────────────────────────────

  it('calls http.request and returns response.data', async () => {
    mockHttp.request.mockResolvedValue({ data: { id: 42 } });
    const result = await request({ method: 'GET', url: '/ping' });
    expect(result).toEqual({ id: 42 });
    expect(mockHttp.request).toHaveBeenCalledWith({ method: 'GET', url: '/ping' });
  });

  it('throws when axios global is missing', async () => {
    vi.resetModules();
    vi.stubGlobal('axios', undefined);
    await expect(import('../client.js')).rejects.toThrow('Axios global not found');
  });

  // ── response interceptor ─────────────────────────────────────────────────

  it('success interceptor passes response through unchanged', () => {
    const res = { data: { id: 1 }, status: 200 };
    expect(capturedSuccessInterceptor(res)).toBe(res);
  });

  // ── error interceptor ─────────────────────────────────────────────────────

  it('interceptor normalizes detail from response data', () => {
    const err = { response: { status: 404, data: { detail: 'Not found' } }, message: 'fail' };
    expect(() => capturedErrorInterceptor(err)).toThrow('Not found');
  });

  it('interceptor falls back to error.message when no detail', () => {
    const err = { response: { status: 500, data: {} }, message: 'Server error' };
    expect(() => capturedErrorInterceptor(err)).toThrow('Server error');
  });

  it('interceptor uses fallback message when neither detail nor message', () => {
    const err = {};
    expect(() => capturedErrorInterceptor(err)).toThrow('Unexpected API error');
  });

  it('interceptor attaches status and data to normalized error', () => {
    const err = { response: { status: 422, data: { detail: 'Invalid' } }, message: 'err' };
    try {
      capturedErrorInterceptor(err);
    } catch (e) {
      expect(e.status).toBe(422);
      expect(e.data).toEqual({ detail: 'Invalid' });
    }
  });

  it('interceptor defaults status to 500 when no response', () => {
    const err = { message: 'Network err' };
    try {
      capturedErrorInterceptor(err);
    } catch (e) {
      expect(e.status).toBe(500);
      expect(e.data).toBeNull();
    }
  });

  // ── streamPost ────────────────────────────────────────────────────────────

  it('streamPost calls fetch with correct method and headers', async () => {
    const encoder = new TextEncoder();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => ({
            read: vi
              .fn()
              .mockResolvedValueOnce({ done: false, value: encoder.encode('data: {"x":1}\n\n') })
              .mockResolvedValueOnce({ done: true })
          })
        }
      })
    );

    await streamPost('/events', { key: 'val' }, vi.fn());

    expect(globalThis.fetch).toHaveBeenCalledWith('/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'val' })
    });
  });

  it('streamPost calls onMessage for each SSE data event', async () => {
    const encoder = new TextEncoder();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => ({
            read: vi
              .fn()
              .mockResolvedValueOnce({
                done: false,
                value: encoder.encode('data: {"step":"start"}\n\ndata: {"step":"end"}\n\n')
              })
              .mockResolvedValueOnce({ done: true })
          })
        }
      })
    );

    const onMessage = vi.fn();
    await streamPost('/stream', {}, onMessage);

    expect(onMessage).toHaveBeenCalledTimes(2);
    expect(onMessage).toHaveBeenNthCalledWith(1, { step: 'start' });
    expect(onMessage).toHaveBeenNthCalledWith(2, { step: 'end' });
  });

  it('streamPost handles events across multiple chunks', async () => {
    const encoder = new TextEncoder();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => ({
            read: vi
              .fn()
              .mockResolvedValueOnce({ done: false, value: encoder.encode('data: {"a":1}\n\n') })
              .mockResolvedValueOnce({ done: false, value: encoder.encode('data: {"a":2}\n\n') })
              .mockResolvedValueOnce({ done: true })
          })
        }
      })
    );

    const onMessage = vi.fn();
    await streamPost('/stream', {}, onMessage);

    expect(onMessage).toHaveBeenCalledTimes(2);
  });

  it('streamPost skips event blocks without a data: line', async () => {
    const encoder = new TextEncoder();
    // A chunk with an empty block followed by a real data event.
    // After split('\n\n'): ['', 'data: {"ok":true}', ''] → pop removes ''
    // forEach sees '' (no data: line → return early) then 'data: {"ok":true}'
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: {
          getReader: () => ({
            read: vi
              .fn()
              .mockResolvedValueOnce({
                done: false,
                value: encoder.encode('\n\ndata: {"ok":true}\n\n')
              })
              .mockResolvedValueOnce({ done: true })
          })
        }
      })
    );

    const onMessage = vi.fn();
    await streamPost('/stream', {}, onMessage);

    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({ ok: true });
  });

  it('streamPost throws when response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, body: null }));
    await expect(streamPost('/stream', {}, vi.fn())).rejects.toThrow(
      'Could not start stream request'
    );
  });

  it('streamPost throws when response has no body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: null }));
    await expect(streamPost('/stream', {}, vi.fn())).rejects.toThrow(
      'Could not start stream request'
    );
  });
});
