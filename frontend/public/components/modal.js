export function createModal({ title, content }) {
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop hidden';
  backdrop.innerHTML = `
    <div class="modal-card" role="dialog" aria-modal="true" aria-label="${title}">
      <div class="modal-head">
        <h3>${title}</h3>
        <button type="button" data-modal-close aria-label="Close modal">x</button>
      </div>
      <div class="modal-body"></div>
    </div>
  `;

  const body = backdrop.querySelector('.modal-body');
  if (typeof content === 'string') {
    body.innerHTML = content;
  } else if (content instanceof HTMLElement) {
    body.appendChild(content);
  }

  const close = () => backdrop.classList.add('hidden');
  const open = () => backdrop.classList.remove('hidden');

  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop || event.target.closest('[data-modal-close]')) {
      close();
    }
  });

  return { element: backdrop, open, close };
}
