import { toast } from './components/toast.js';
import { initDashboardPage } from './pages/dashboard/dashboard.page.js';
import { initGeneratorPage } from './pages/generator/generator.page.js';
import { initReportsPage } from './pages/reports/reports.page.js';
import { mount as mountEditorPage } from './pages/robot-editor/editor.page.js';
import { initScannerPage } from './pages/scanner/scanner.page.js';
import { initRouter, navigateToTab } from './router.js';
import { store } from './state/store.js';

const dashboardPage = initDashboardPage({ store });
const generatorPage = initGeneratorPage({ store });
const reportsPage = initReportsPage({ store });
const scannerPage = initScannerPage({
  store,
  onRecreateRequested: async ({ projectId, feedback, testIds }) => {
    await generatorPage.generateFromExecutionFeedback(projectId, feedback, testIds);
    navigateToTab('generate');
  }
});

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
