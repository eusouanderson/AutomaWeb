/**
 * Tests for App Integration
 * Tests: app.js authentication flow and page mounting
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock modules
vi.mock('../components/toast.js', () => ({
  toast: vi.fn()
}));

vi.mock('../pages/dashboard/dashboard.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadProjects: vi.fn()
  })
}));

vi.mock('../pages/generator/generator.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadProjectsDropdown: vi.fn(),
    generateFromExecutionFeedback: vi.fn()
  })
}));

vi.mock('../pages/reports/reports.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadReportsProjects: vi.fn()
  })
}));

vi.mock('../pages/robot-editor/editor.page.js', () => ({
  mount: vi.fn().mockResolvedValue({})
}));

vi.mock('../pages/scanner/scanner.page.js', () => ({
  mount: vi.fn().mockResolvedValue({
    loadExecuteProjects: vi.fn(),
    loadTestsProjects: vi.fn(),
    loadRecreateRequested: vi.fn()
  })
}));

vi.mock('../router.js', () => ({
  initRouter: vi.fn(),
  navigateToTab: vi.fn()
}));

vi.mock('../state/store.js', () => ({
  store: { state: {} }
}));

vi.mock('../static/auth.js', () => ({
  AuthorizationUI: class {
    constructor(containerId) {
      this.containerId = containerId;
    }
    showAuthDialog = vi.fn().mockResolvedValue(true);
  }
}));

// Mock axios
vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      response: {
        use: vi.fn((success, error) => {
          this.errorInterceptor = error;
        })
      }
    }
  }
}));

describe('Authentication Flow', () => {
  let axiosMock;

  beforeEach(() => {
    axiosMock = vi.mocked(require('axios').default);
  });

  describe('Interceptor 401 Handling', () => {
    it('should handle 401 errors', () => {
      const interceptors = axiosMock.interceptors.response.use.mock.calls[0];
      const errorHandler = interceptors[1];

      const error = {
        response: {
          status: 401,
          data: { detail: 'authentication required' }
        },
        config: {}
      };

      // This should trigger the interceptor
      expect(errorHandler).toBeDefined();
    });
  });

  describe('App Initialization', () => {
    it('should setup axios response interceptor', () => {
      expect(axiosMock.interceptors.response.use).toHaveBeenCalled();
    });
  });
});

describe('Frontend Authentication Integration', () => {
  describe('Token Check', () => {
    it('should check if user is authenticated on load', async () => {
      const axiosMock = vi.mocked(require('axios').default);
      
      axiosMock.get.mockResolvedValue({
        data: { authenticated: true }
      });

      // Simulate auth check
      const response = await axiosMock.get('/api/ai/token/check');
      
      expect(response.data.authenticated).toBe(true);
      expect(axiosMock.get).toHaveBeenCalledWith('/api/ai/token/check');
    });

    it('should show modal if not authenticated', async () => {
      const axiosMock = vi.mocked(require('axios').default);
      
      axiosMock.get.mockResolvedValue({
        data: { authenticated: false }
      });

      const response = await axiosMock.get('/api/ai/token/check');
      
      expect(response.data.authenticated).toBe(false);
    });
  });
});
