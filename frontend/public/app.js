import { toast } from './components/toast.js';
import { initDashboardPage } from './pages/dashboard/dashboard.page.js';
import { initGeneratorPage } from './pages/generator/generator.page.js';
import { initScannerPage } from './pages/scanner/scanner.page.js';
import { initRouter, navigateToTab } from './router.js';
import { store } from './state/store.js';

const dashboardPage = initDashboardPage({ store });
const generatorPage = initGeneratorPage({ store });
const scannerPage = initScannerPage({
  store,
  onRecreateRequested: async ({ projectId, feedback }) => {
    await generatorPage.generateFromExecutionFeedback(projectId, feedback);
    navigateToTab('generate');
  }
});

await dashboardPage.loadProjects();
await generatorPage.loadProjectsDropdown();
await scannerPage.loadExecuteProjects();

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
  }
});

toast('Frontend carregado', 'info');
