import { toast } from './components/toast.js';
import { mount as mountDashboardPage } from './pages/dashboard/dashboard.page.js';
import { mount as mountGeneratorPage } from './pages/generator/generator.page.js';
import { mount as mountReportsPage } from './pages/reports/reports.page.js';
import { mount as mountEditorPage } from './pages/robot-editor/editor.page.js';
import { mount as mountScannerPage } from './pages/scanner/scanner.page.js';
import { initRouter, navigateToTab } from './router.js';
import { store } from './state/store.js';

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
