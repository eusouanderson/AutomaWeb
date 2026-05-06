import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthorizationUI, CopilotAuthManager } from './auth.js';

async function flushMicrotasks() {
  await Promise.resolve();
  await Promise.resolve();
}

describe('CopilotAuthManager', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    global.axios = {
      get: vi.fn(),
      post: vi.fn(),
    };
  });

  it('checkAuthentication returns true when API says authenticated', async () => {
    axios.get.mockResolvedValue({ data: { authenticated: true } });
    const manager = new CopilotAuthManager();

    await expect(manager.checkAuthentication()).resolves.toBe(true);
    expect(axios.get).toHaveBeenCalledWith('/api/ai/token/check');
  });

  it('checkAuthentication returns false when API call fails', async () => {
    axios.get.mockRejectedValue(new Error('network'));
    const manager = new CopilotAuthManager();

    await expect(manager.checkAuthentication()).resolves.toBe(false);
  });

  it('startAuthorization returns mapped payload on success', async () => {
    axios.post.mockResolvedValue({
      data: {
        verification_uri: 'https://github.com/login/device',
        user_code: 'ABCD-EFGH',
        device_code: 'device-code',
        expires_in: 900,
      },
    });

    const manager = new CopilotAuthManager();
    const result = await manager.startAuthorization();

    expect(result).toEqual({
      success: true,
      verification_uri: 'https://github.com/login/device',
      user_code: 'ABCD-EFGH',
      device_code: 'device-code',
      expires_in: 900,
    });
    expect(axios.post).toHaveBeenCalledWith('/api/ai/authorize', { enterprise_url: null });
  });

  it('startAuthorization returns error from response detail', async () => {
    axios.post.mockRejectedValue({ response: { data: { detail: 'bad request' } } });
    const manager = new CopilotAuthManager();

    await expect(manager.startAuthorization()).resolves.toEqual({
      success: false,
      error: 'bad request',
    });
  });

  it('pollDeviceCode resolves when authenticated and reports progress', async () => {
    axios.post.mockResolvedValue({ data: { authenticated: true, message: 'ok' } });
    const manager = new CopilotAuthManager();
    const onProgress = vi.fn();

    const result = await manager.pollDeviceCode('device-1', onProgress);

    expect(result).toEqual({ success: true, message: 'ok' });
    expect(onProgress).toHaveBeenCalledWith(
      expect.objectContaining({ authenticated: true, message: 'ok' })
    );
  });

  it('pollDeviceCode rejects on timeout when attempts exceed max', async () => {
    const manager = new CopilotAuthManager();
    manager.maxPollAttempts = 0;

    await expect(manager.pollDeviceCode('device-timeout')).rejects.toThrow('Authorization timeout');
  });

  it('pollDeviceCode increases interval on slow_down responses', async () => {
    vi.useFakeTimers();
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout');

    axios.post
      .mockResolvedValueOnce({ data: { authenticated: false, message: 'wait', slow_down: true } })
      .mockResolvedValueOnce({ data: { authenticated: true, message: 'done' } });

    const manager = new CopilotAuthManager();
    const promise = manager.pollDeviceCode('device-slow');

    await flushMicrotasks();
    expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 10000);

    await vi.advanceTimersByTimeAsync(10000);
    await expect(promise).resolves.toEqual({ success: true, message: 'done' });
  });

  it('pollDeviceCode rejects when poll request fails', async () => {
    axios.post.mockRejectedValue(new Error('poll failed'));
    const manager = new CopilotAuthManager();

    await expect(manager.pollDeviceCode('device-error')).rejects.toThrow('poll failed');
  });

  it('authorize opens verification URL and delegates to pollDeviceCode', async () => {
    const manager = new CopilotAuthManager();
    vi.spyOn(manager, 'startAuthorization').mockResolvedValue({
      success: true,
      verification_uri: 'https://github.com/login/device',
      device_code: 'dc-1',
    });
    vi.spyOn(manager, 'pollDeviceCode').mockResolvedValue({ success: true, message: 'ok' });
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const onProgress = vi.fn();

    const result = await manager.authorize(onProgress);

    expect(openSpy).toHaveBeenCalledWith(
      'https://github.com/login/device',
      '_blank',
      'width=500,height=700'
    );
    expect(manager.pollDeviceCode).toHaveBeenCalledWith('dc-1', onProgress);
    expect(result).toEqual({ success: true, message: 'ok' });
  });

  it('authorize throws when startAuthorization fails', async () => {
    const manager = new CopilotAuthManager();
    vi.spyOn(manager, 'startAuthorization').mockResolvedValue({ success: false, error: 'no auth' });

    await expect(manager.authorize()).rejects.toThrow('no auth');
  });
});

describe('AuthorizationUI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    document.body.innerHTML = '<div id="auth-container"></div>';
    Object.defineProperty(global.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('rejects showAuthDialog when startAuthorization fails', async () => {
    const ui = new AuthorizationUI('auth-container');
    vi.spyOn(ui.authManager, 'startAuthorization').mockResolvedValue({
      success: false,
      error: 'cannot start',
    });

    await expect(ui.showAuthDialog()).rejects.toThrow('cannot start');
  });

  it('copies user code to clipboard when copy button is clicked', async () => {
    vi.useFakeTimers();
    const ui = new AuthorizationUI('auth-container');
    vi.spyOn(ui.authManager, 'startAuthorization').mockResolvedValue({
      success: true,
      verification_uri: 'https://github.com/login/device',
      user_code: 'ZXCV-1234',
      device_code: 'dc-2',
      expires_in: 900,
    });

    const dialogPromise = ui.showAuthDialog().catch(() => undefined);

    await flushMicrotasks();
    const copyBtn = document.getElementById('copy-code-btn');
    expect(copyBtn).toBeTruthy();
    copyBtn.click();

    await Promise.resolve();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('ZXCV-1234');
    expect(copyBtn.textContent).toContain('Copiado');

    await vi.advanceTimersByTimeAsync(2000);
    expect(copyBtn.textContent).toContain('Copiar Código');

    document.querySelector('.auth-modal-close').click();
    await dialogPromise;
  });

  it('resolves when already authenticated after opening github flow', async () => {
    vi.useFakeTimers();
    const ui = new AuthorizationUI('auth-container');

    vi.spyOn(ui.authManager, 'startAuthorization').mockResolvedValue({
      success: true,
      verification_uri: 'https://github.com/login/device',
      user_code: 'AAAA-BBBB',
      device_code: 'dc-3',
      expires_in: 900,
    });
    vi.spyOn(ui.authManager, 'checkAuthentication').mockResolvedValue(true);
    vi.spyOn(ui.authManager, 'pollDeviceCode').mockReturnValue(new Promise(() => {}));
    vi.spyOn(window, 'open').mockImplementation(() => null);

    const promise = ui.showAuthDialog();
    await flushMicrotasks();
    document.getElementById('auth-github-btn').click();

    await vi.advanceTimersByTimeAsync(500);
    await expect(promise).resolves.toBe(true);
  });

  it('updates progress and resolves when poll succeeds', async () => {
    vi.useFakeTimers();
    const ui = new AuthorizationUI('auth-container');

    vi.spyOn(ui.authManager, 'startAuthorization').mockResolvedValue({
      success: true,
      verification_uri: 'https://github.com/login/device',
      user_code: 'POLL-OK',
      device_code: 'dc-4',
      expires_in: 900,
    });
    vi.spyOn(ui.authManager, 'checkAuthentication').mockResolvedValue(false);
    vi.spyOn(window, 'open').mockImplementation(() => null);

    let resolvePoll;
    vi.spyOn(ui.authManager, 'pollDeviceCode').mockImplementation((_deviceCode, onProgress) => {
      onProgress({ progress: 55, message: 'waiting' });
      return new Promise((resolve) => {
        resolvePoll = resolve;
      });
    });

    const promise = ui.showAuthDialog();
    await flushMicrotasks();
    document.getElementById('auth-github-btn').click();

    await vi.advanceTimersByTimeAsync(500);

    const fill = document.getElementById('auth-progress-fill');
    expect(fill.style.width).toBe('55%');

    resolvePoll({ success: true, message: 'done' });
    await expect(promise).resolves.toBe(true);
  });

  it('rejects and shows error message when poll fails', async () => {
    vi.useFakeTimers();
    const ui = new AuthorizationUI('auth-container');

    vi.spyOn(ui.authManager, 'startAuthorization').mockResolvedValue({
      success: true,
      verification_uri: 'https://github.com/login/device',
      user_code: 'POLL-ERR',
      device_code: 'dc-5',
      expires_in: 900,
    });
    vi.spyOn(ui.authManager, 'checkAuthentication').mockResolvedValue(false);
    vi.spyOn(window, 'open').mockImplementation(() => null);

    let rejectPoll;
    vi.spyOn(ui.authManager, 'pollDeviceCode').mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectPoll = reject;
        })
    );

    const promise = ui.showAuthDialog();
    await flushMicrotasks();
    document.getElementById('auth-github-btn').click();

    await vi.advanceTimersByTimeAsync(500);
    rejectPoll(new Error('poll error'));
    await flushMicrotasks();
    await expect(promise).rejects.toThrow('poll error');

    const msg = document.getElementById('auth-status-msg').textContent;
    expect(msg).toContain('Erro: poll error');
  });

  it('rejects when close button is clicked', async () => {
    const ui = new AuthorizationUI('auth-container');
    vi.spyOn(ui.authManager, 'startAuthorization').mockResolvedValue({
      success: true,
      verification_uri: 'https://github.com/login/device',
      user_code: 'CLOSE-BTN',
      device_code: 'dc-6',
      expires_in: 900,
    });

    const promise = ui.showAuthDialog();
    await flushMicrotasks();
    document.querySelector('.auth-modal-close').click();

    await expect(promise).rejects.toThrow('Authorization cancelled');
  });

  it('rejects when clicking modal backdrop', async () => {
    const ui = new AuthorizationUI('auth-container');
    vi.spyOn(ui.authManager, 'startAuthorization').mockResolvedValue({
      success: true,
      verification_uri: 'https://github.com/login/device',
      user_code: 'BACKDROP',
      device_code: 'dc-7',
      expires_in: 900,
    });

    const promise = ui.showAuthDialog();
    await flushMicrotasks();
    const modal = document.querySelector('.auth-modal');
    modal.dispatchEvent(new MouseEvent('click', { bubbles: true }));

    await expect(promise).rejects.toThrow('Authorization cancelled');
  });

  it('ensureAuthenticated returns true when already authenticated', async () => {
    const ui = new AuthorizationUI('auth-container');
    vi.spyOn(ui.authManager, 'checkAuthentication').mockResolvedValue(true);

    await expect(ui.ensureAuthenticated()).resolves.toBe(true);
  });

  it('ensureAuthenticated opens dialog and returns true when auth succeeds', async () => {
    const ui = new AuthorizationUI('auth-container');
    vi.spyOn(ui.authManager, 'checkAuthentication').mockResolvedValue(false);
    vi.spyOn(ui, 'showAuthDialog').mockResolvedValue(true);

    await expect(ui.ensureAuthenticated()).resolves.toBe(true);
    expect(ui.showAuthDialog).toHaveBeenCalledTimes(1);
  });

  it('ensureAuthenticated returns false when dialog fails', async () => {
    const ui = new AuthorizationUI('auth-container');
    vi.spyOn(ui.authManager, 'checkAuthentication').mockResolvedValue(false);
    vi.spyOn(ui, 'showAuthDialog').mockRejectedValue(new Error('denied'));

    await expect(ui.ensureAuthenticated()).resolves.toBe(false);
  });
});
