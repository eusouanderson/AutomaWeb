import { toast } from './components/toast.js';
import { mount as mountDashboardPage } from './pages/dashboard/dashboard.page.js';
import { mount as mountGeneratorPage } from './pages/generator/generator.page.js';
import { mount as mountReportsPage } from './pages/reports/reports.page.js';
import { mount as mountEditorPage } from './pages/robot-editor/editor.page.js';
import { mount as mountScannerPage } from './pages/scanner/scanner.page.js';
import { initRouter, navigateToTab } from './router.js';
import { store } from './state/store.js';
import { AuthorizationUI } from './static/auth.js?v=2';

// ============================================================================
// Setup Axios Interceptor for Authentication Errors
// ============================================================================

const authUI = new AuthorizationUI('auth-container');

console.log('✓ AuthorizationUI initialized');
console.log('auth-container element:', document.getElementById('auth-container'));

axios.interceptors.response.use(
  response => response,
  async error => {
    console.log('❌ Response interceptor triggered');
    console.log('Status:', error.response?.status);
    console.log('Message:', error.response?.data?.detail);
    
    // Handle 401 Unauthorized (Authentication Required)
    if (error.response?.status === 401) {
      const message = error.response?.data?.detail || 'Autenticação necessária';
      console.log('🔐 401 detected. Message:', message);
      
      if (message.includes('authentication required') || message.includes('authorize')) {
        try {
          console.log('📋 Showing auth dialog...');
          // Show auth dialog
          await authUI.showAuthDialog();
          console.log('✓ Auth dialog resolved. Retrying request...');
          // Retry the original request after successful auth
          return axios(error.config);
        } catch (authError) {
          console.error('❌ Auth dialog error:', authError);
          toast('❌ Autenticação cancelada', 'error');
          return Promise.reject(authError);
        }
      }
    }
    
    // Re-throw other errors
    return Promise.reject(error);
  }
);

// ============================================================================
// Check Authentication on App Load
// ============================================================================

async function ensureAuthentication() {
  try {
    console.log('🔐 Checking Copilot authentication on app load...');
    const response = await axios.get('/api/ai/token/check');
    console.log('Token check response:', response.data);
    
    // Check if actually authenticated
    if (response.data.authenticated === true) {
      console.log('✓ User is authenticated');
      return true;
    } else {
      console.log('⚠️ User not authenticated (token_check returned false). Showing auth dialog...');
      throw new Error('Not authenticated');
    }
  } catch (error) {
    console.log('⚠️ Not authenticated. Showing auth dialog...');
    try {
      await authUI.showAuthDialog();
      console.log('✓ Modal closed. Verifying authentication...');
      
      // After modal closes, verify that authentication was actually successful
      const verifyResponse = await axios.get('/api/ai/token/check');
      console.log('Verification response:', verifyResponse.data);
      
      if (verifyResponse.data.authenticated === true) {
        console.log('✓ User authenticated successfully');
        return true;
      } else {
        console.error('❌ Authentication modal closed but token check still returns false');
        toast('❌ Falha na autenticação. Tente novamente.', 'error');
        return false;
      }
    } catch (authError) {
      console.error('❌ Authentication failed:', authError);
      toast('❌ Autenticação obrigatória para usar a aplicação', 'error');
      return false;
    }
  }
}

// Ensure user is authenticated before loading app
const isAuthenticated = await ensureAuthentication();
if (!isAuthenticated) {
  // Keep showing the auth dialog until user authenticates
  let retries = 0;
  while (!isAuthenticated && retries < 3) {
    retries++;
    await new Promise(resolve => setTimeout(resolve, 1000));
    const auth = await ensureAuthentication();
    if (auth) break;
  }
}

console.log('✓ Authentication verified. Loading app...');

// ============================================================================
// Mount Pages
// ============================================================================

const dashboardPage = await mountDashboardPage(document.getElementById('projects-tab'), { store });
const generatorPage = await mountGeneratorPage(document.getElementById('generate-tab'), { store });
const reportsPage = await mountReportsPage(document.getElementById('reports-tab'), { store });
const scannerPage = await mountScannerPage(
  {
    testsRoot: document.getElementById('tests-tab'),
    executeRoot: document.getElementById('execute-tab')
  },
  {
    store,
    onRecreateRequested: async ({ projectId, feedback, testIds }) => {
      await generatorPage.generateFromExecutionFeedback(projectId, feedback, testIds);
      navigateToTab('generate');
    }
  }
);

await dashboardPage.loadProjects();
await generatorPage.loadProjectsDropdown();
await scannerPage.loadExecuteProjects();
await reportsPage.loadReportsProjects();

const editorRoot = document.getElementById('editor-tab');
if (editorRoot) {
  await mountEditorPage(editorRoot, { store });
}

initRouter({
  onTabChange: async (tabName) => {
    if (tabName === 'projects') {
      await dashboardPage.loadProjects();
    }

    if (tabName === 'generate') {
      await generatorPage.loadProjectsDropdown();
    }

    if (tabName === 'tests') {
      await scannerPage.loadTestsProjects();
    }

    if (tabName === 'execute') {
      await scannerPage.loadExecuteProjects();
    }

    if (tabName === 'reports') {
      await reportsPage.loadReportsProjects();
    }
  }
});

toast('Frontend carregado', 'info');
