/**
 * Tests for Copilot Authentication
 * Tests: CopilotAuthManager and AuthorizationUI classes
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthorizationUI, CopilotAuthManager } from '../auth.js';

// Mock axios
vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      response: {
        use: vi.fn()
      }
    }
  }
}));

describe('CopilotAuthManager', () => {
  let authManager;

  beforeEach(() => {
    authManager = new CopilotAuthManager();
  });

  describe('checkAuthentication', () => {
    it('should return true when user is authenticated', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.get.mockResolvedValue({
        data: { authenticated: true }
      });

      const result = await authManager.checkAuthentication();
      expect(result).toBe(true);
      expect(mockAxios.default.get).toHaveBeenCalledWith('/api/ai/token/check');
    });

    it('should return false when user is not authenticated', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.get.mockResolvedValue({
        data: { authenticated: false }
      });

      const result = await authManager.checkAuthentication();
      expect(result).toBe(false);
    });

    it('should return false on error', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.get.mockRejectedValue(new Error('Network error'));

      const result = await authManager.checkAuthentication();
      expect(result).toBe(false);
    });
  });

  describe('startAuthorization', () => {
    it('should return device code information on success', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockResolvedValue({
        data: {
          verification_uri: 'https://github.com/login/device',
          user_code: '1234-5678',
          device_code: 'ov_device_xyz',
          expires_in: 900
        }
      });

      const result = await authManager.startAuthorization();
      
      expect(result.success).toBe(true);
      expect(result.verification_uri).toBe('https://github.com/login/device');
      expect(result.user_code).toBe('1234-5678');
      expect(result.device_code).toBe('ov_device_xyz');
      expect(result.expires_in).toBe(900);
      expect(mockAxios.default.post).toHaveBeenCalledWith('/api/ai/authorize', {
        enterprise_url: null
      });
    });

    it('should return error on failure', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockRejectedValue({
        response: { data: { detail: 'Server error' } }
      });

      const result = await authManager.startAuthorization();
      
      expect(result.success).toBe(false);
      expect(result.error).toBe('Server error');
    });

    it('should return error with fallback message', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockRejectedValue(
        new Error('Network error')
      );

      const result = await authManager.startAuthorization();
      
      expect(result.success).toBe(false);
      expect(result.error).toBe('Network error');
    });
  });

  describe('pollDeviceCode', () => {
    it('should resolve when authenticated', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockResolvedValue({
        data: {
          authenticated: true,
          message: 'Authorization successful'
        }
      });

      const result = await authManager.pollDeviceCode('device_code_123');
      
      expect(result.success).toBe(true);
      expect(result.message).toBe('Authorization successful');
    });

    it('should continue polling while authorization_pending', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post
        .mockResolvedValueOnce({
          data: {
            authenticated: false,
            message: 'Waiting for authorization'
          }
        })
        .mockResolvedValueOnce({
          data: {
            authenticated: false,
            message: 'Still waiting'
          }
        })
        .mockResolvedValueOnce({
          data: {
            authenticated: true,
            message: 'Success'
          }
        });

      const result = await authManager.pollDeviceCode('device_code_123');
      
      expect(result.success).toBe(true);
      expect(mockAxios.default.post).toHaveBeenCalledTimes(3);
    });

    it('should timeout after max attempts', async () => {
      const mockAxios = await import('axios');
      authManager.maxPollAttempts = 2;
      
      mockAxios.default.post.mockResolvedValue({
        data: {
          authenticated: false,
          message: 'Still waiting'
        }
      });

      try {
        await authManager.pollDeviceCode('device_code_123');
        expect.fail('Should have thrown timeout error');
      } catch (error) {
        expect(error.message).toBe('Authorization timeout');
      }
    });

    it('should call onProgress callback', async () => {
      const mockAxios = await import('axios');
      const progressCallback = vi.fn();
      
      mockAxios.default.post.mockResolvedValue({
        data: {
          authenticated: true,
          message: 'Success'
        }
      });

      await authManager.pollDeviceCode('device_code_123', progressCallback);
      
      expect(progressCallback).toHaveBeenCalled();
      expect(progressCallback.mock.calls[0][0]).toMatchObject({
        authenticated: true,
        message: 'Success',
        progress: expect.any(Number)
      });
    });

    it('should handle poll errors', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockRejectedValue(new Error('Poll error'));

      try {
        await authManager.pollDeviceCode('device_code_123');
        expect.fail('Should have thrown error');
      } catch (error) {
        expect(error.message).toBe('Poll error');
      }
    });
  });

  describe('authorize', () => {
    it('should complete full authorization flow', async () => {
      const mockAxios = await import('axios');
      global.window.open = vi.fn();

      mockAxios.default.post
        .mockResolvedValueOnce({
          data: {
            verification_uri: 'https://github.com/login/device',
            user_code: '1234-5678',
            device_code: 'device_xyz',
            expires_in: 900
          }
        })
        .mockResolvedValueOnce({
          data: {
            authenticated: true,
            message: 'Success'
          }
        });

      const result = await authManager.authorize();
      
      expect(result.success).toBe(true);
      expect(global.window.open).toHaveBeenCalledWith(
        'https://github.com/login/device',
        '_blank',
        'width=500,height=700'
      );
    });

    it('should fail if startAuthorization fails', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockRejectedValue(new Error('Server error'));

      try {
        await authManager.authorize();
        expect.fail('Should have thrown error');
      } catch (error) {
        expect(error.message).toBe('Server error');
      }
    });
  });
});

describe('AuthorizationUI', () => {
  let authUI;
  let container;

  beforeEach(() => {
    container = document.createElement('div');
    container.id = 'auth-container';
    document.body.appendChild(container);
    authUI = new AuthorizationUI('auth-container');
  });

  afterEach(() => {
    document.body.removeChild(container);
    vi.clearAllMocks();
  });

  describe('showAuthDialog', () => {
    it('should create and display modal', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockResolvedValue({
        data: {
          verification_uri: 'https://github.com/login/device',
          user_code: '1234-5678',
          device_code: 'device_xyz',
          expires_in: 900
        }
      });

      // Start modal but don't wait for user interaction
      const modalPromise = authUI.showAuthDialog();
      
      // Give DOM time to render
      await new Promise(resolve => setTimeout(resolve, 100));

      // Check modal exists
      const modal = document.querySelector('.auth-modal');
      expect(modal).toBeDefined();
      expect(modal.textContent).toContain('1234-5678');
      expect(modal.textContent).toContain('github.com/login/device');

      // Clean up
      const closeBtn = document.querySelector('.auth-modal-close');
      closeBtn?.click();
    });

    it('should handle close button', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.post.mockResolvedValue({
        data: {
          verification_uri: 'https://github.com/login/device',
          user_code: '1234-5678',
          device_code: 'device_xyz',
          expires_in: 900
        }
      });

      const modalPromise = authUI.showAuthDialog();
      
      await new Promise(resolve => setTimeout(resolve, 100));

      const closeBtn = document.querySelector('.auth-modal-close');
      closeBtn.click();

      try {
        await modalPromise;
        expect.fail('Should have thrown error');
      } catch (error) {
        expect(error.message).toBe('Authorization cancelled');
      }
    });

    it('should copy device code to clipboard', async () => {
      const mockAxios = await import('axios');
      navigator.clipboard = {
        writeText: vi.fn().mockResolvedValue(undefined)
      };

      mockAxios.default.post.mockResolvedValue({
        data: {
          verification_uri: 'https://github.com/login/device',
          user_code: '1234-5678',
          device_code: 'device_xyz',
          expires_in: 900
        }
      });

      const modalPromise = authUI.showAuthDialog();
      await new Promise(resolve => setTimeout(resolve, 100));

      const copyBtn = document.getElementById('copy-code-btn');
      copyBtn.click();

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('1234-5678');

      const closeBtn = document.querySelector('.auth-modal-close');
      closeBtn.click();
    });
  });

  describe('ensureAuthenticated', () => {
    it('should return true if already authenticated', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.get.mockResolvedValue({
        data: { authenticated: true }
      });

      const result = await authUI.ensureAuthenticated();
      expect(result).toBe(true);
    });

    it('should show dialog if not authenticated', async () => {
      const mockAxios = await import('axios');
      mockAxios.default.get.mockResolvedValue({
        data: { authenticated: false }
      });

      mockAxios.default.post.mockResolvedValue({
        data: {
          verification_uri: 'https://github.com/login/device',
          user_code: '1234-5678',
          device_code: 'device_xyz',
          expires_in: 900
        }
      });

      const modalPromise = authUI.ensureAuthenticated();
      await new Promise(resolve => setTimeout(resolve, 100));

      const modal = document.querySelector('.auth-modal');
      expect(modal).toBeDefined();

      const closeBtn = document.querySelector('.auth-modal-close');
      closeBtn.click();

      try {
        await modalPromise;
      } catch {
        // Expected to fail since we closed the modal
      }
    });
  });
});
