const TAB_IDS = new Set(['projects', 'generate', 'tests', 'execute', 'editor', 'reports']);

function getTabFromHash() {
  const hash = globalThis.location.hash || '#projects';
  const name = hash.replace('#', '');
  return TAB_IDS.has(name) ? name : 'projects';
}

function showTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.tab === tabName);
  });

  document.querySelectorAll('.tab-content').forEach((content) => {
    content.classList.toggle('active', content.id === `${tabName}-tab`);
  });
}

export function navigateToTab(tabName) {
  if (!TAB_IDS.has(tabName)) {
    return;
  }
  globalThis.location.hash = tabName;
}

export function initRouter({ onTabChange }) {
  const applyCurrentRoute = async () => {
    const tabName = getTabFromHash();
    showTab(tabName);
    await onTabChange?.(tabName);
  };

  document.querySelectorAll('.tab-btn').forEach((button) => {
    button.addEventListener('click', () => {
      navigateToTab(button.dataset.tab);
    });
  });

  globalThis.addEventListener('hashchange', () => {
    applyCurrentRoute();
  });

  if (!globalThis.location.hash) {
    globalThis.location.hash = 'projects';
  }

  applyCurrentRoute();
}
