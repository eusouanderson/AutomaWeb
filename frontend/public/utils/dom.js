const templateCache = new Map();

export function qs(selector, root = document) {
  return root.querySelector(selector);
}

export function qsa(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

export function renderHTML(root, html) {
  root.innerHTML = html;
}

export async function loadTemplate(path) {
  if (templateCache.has(path)) {
    return templateCache.get(path);
  }
  const response = await fetch(path);
  const html = await response.text();
  templateCache.set(path, html);
  return html;
}
