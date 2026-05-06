import { beforeEach, describe, expect, it, vi } from 'vitest';

const mountDashboardPage = vi.fn().mockResolvedValue({
  loadProjects: vi.fn().mockResolvedValue(undefined),
});
const mountGeneratorPage = vi.fn().mockResolvedValue({
  loadProjectsDropdown: vi.fn().mockResolvedValue(undefined),
  generateFromExecutionFeedback: vi.fn().mockResolvedValue(undefined),
});
const mountReportsPage = vi.fn().mockResolvedValue({
  loadReportsProjects: vi.fn().mockResolvedValue(undefined),
});
const mountScannerPage = vi.fn().mockResolvedValue({
  loadTestsProjects: vi.fn().mockResolvedValue(undefined),
  loadExecuteProjects: vi.fn().mockResolvedValue(undefined),
});
const mountEditorPage = vi.fn().mockResolvedValue(undefined);
const initRouter = vi.fn();
const navigateToTab = vi.fn();
const toast = vi.fn();

function setupBaseMocks() {
  vi.doMock('../state/store.js', () => ({ store: {} }));
  vi.doMock('../components/toast.js', () => ({ toast }));
  vi.doMock('../router.js', () => ({ initRouter, navigateToTab }));
  vi.doMock('../pages/dashboard/dashboard.page.js', () => ({ mount: mountDashboardPage }));
  vi.doMock('../pages/generator/generator.page.js', () => ({ mount: mountGeneratorPage }));
  vi.doMock('../pages/scanner/scanner.page.js', () => ({ mount: mountScannerPage }));
  vi.doMock('../pages/reports/reports.page.js', () => ({ mount: mountReportsPage }));
  vi.doMock('../pages/robot-editor/editor.page.js', () => ({ mount: mountEditorPage }));
}

async function importAppWithAuth({ getImpl, showAuthDialogImpl }) {
  vi.resetModules();
  vi.clearAllMocks();

  document.body.innerHTML = `
    <div id="auth-container"></div>
    <div id="projects-tab"></div>
    <div id="generate-tab"></div>
    <div id="tests-tab"></div>
    <div id="execute-tab"></div>
    <div id="reports-tab"></div>
    <div id="editor-tab"></div>
  `;

  setupBaseMocks();

  const showAuthDialog = vi.fn(showAuthDialogImpl);
  vi.doMock('../static/auth.js', () => ({
    AuthorizationUI: class {
      constructor() {}
      showAuthDialog = showAuthDialog;
    },
  }));

  const interceptorUse = vi.fn();
  const axiosMock = vi.fn((config) => Promise.resolve({ data: { retried: true }, config }));
  axiosMock.get = vi.fn(getImpl);
  axiosMock.interceptors = {
    response: { use: interceptorUse },
  };

  global.axios = axiosMock;

  await import('../app.js');

  return {
    axiosMock,
    interceptorRejectHandler: interceptorUse.mock.calls[0][1],
    showAuthDialog,
  };
}

describe('app.js auth and interceptor flows', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn) => {
      fn();
      return 0;
    });
  });

  it('retries request through interceptor when 401 says authentication required', async () => {
    const { interceptorRejectHandler, showAuthDialog, axiosMock } = await importAppWithAuth({
      getImpl: async () => ({ data: { authenticated: true } }),
      showAuthDialogImpl: async () => true,
    });

    const error = {
      response: { status: 401, data: { detail: 'authentication required' } },
      config: { url: '/api/x', method: 'get' },
    };

    const result = await interceptorRejectHandler(error);

    expect(showAuthDialog).toHaveBeenCalledTimes(1);
    expect(axiosMock).toHaveBeenCalledWith(error.config);
    expect(result).toMatchObject({ data: { retried: true } });
  });

  it('shows cancellation toast when auth dialog fails during 401 handling', async () => {
    const { interceptorRejectHandler, showAuthDialog } = await importAppWithAuth({
      getImpl: async () => ({ data: { authenticated: true } }),
      showAuthDialogImpl: async () => {
        throw new Error('cancelled');
      },
    });

    const error = {
      response: { status: 401, data: { detail: 'authorize now' } },
      config: { url: '/api/y', method: 'post' },
    };

    await expect(interceptorRejectHandler(error)).rejects.toThrow('cancelled');
    expect(showAuthDialog).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith('❌ Autenticação cancelada', 'error');
  });

  it('rethrows non-auth interceptor errors without opening auth dialog', async () => {
    const { interceptorRejectHandler, showAuthDialog } = await importAppWithAuth({
      getImpl: async () => ({ data: { authenticated: true } }),
      showAuthDialogImpl: async () => true,
    });

    const error = {
      response: { status: 500, data: { detail: 'server error' } },
      config: { url: '/api/z', method: 'get' },
    };

    await expect(interceptorRejectHandler(error)).rejects.toBe(error);
    expect(showAuthDialog).not.toHaveBeenCalled();
  });

  it('authenticates successfully after modal when initial token check throws', async () => {
    const getMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ data: { authenticated: true } });

    const { showAuthDialog } = await importAppWithAuth({
      getImpl: getMock,
      showAuthDialogImpl: async () => true,
    });

    expect(showAuthDialog).toHaveBeenCalledTimes(1);
    expect(getMock).toHaveBeenCalledTimes(2);
    expect(toast).not.toHaveBeenCalledWith('❌ Falha na autenticação. Tente novamente.', 'error');
    expect(initRouter).toHaveBeenCalledTimes(1);
  });

  it('enters retry loop and eventually authenticates after initial false check', async () => {
    const authSequence = [
      { data: { authenticated: false } },
      { data: { authenticated: false } },
      { data: { authenticated: true } },
    ];

    const { showAuthDialog, axiosMock } = await importAppWithAuth({
      getImpl: async () => authSequence.shift() ?? { data: { authenticated: true } },
      showAuthDialogImpl: async () => true,
    });

    expect(showAuthDialog).toHaveBeenCalled();
    expect(setTimeout).toHaveBeenCalled();
    expect(axiosMock.get).toHaveBeenCalledWith('/api/ai/token/check');
    expect(toast).toHaveBeenCalledWith('❌ Falha na autenticação. Tente novamente.', 'error');
    expect(initRouter).toHaveBeenCalledTimes(1);
  });

  it('returns false and shows mandatory-auth toast when modal throws in ensureAuthentication', async () => {
    const { showAuthDialog } = await importAppWithAuth({
      getImpl: async () => ({ data: { authenticated: false } }),
      showAuthDialogImpl: async () => {
        throw new Error('modal failed');
      },
    });

    expect(showAuthDialog).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(
      '❌ Autenticação obrigatória para usar a aplicação',
      'error'
    );
    expect(setTimeout).toHaveBeenCalled();
  });
});
