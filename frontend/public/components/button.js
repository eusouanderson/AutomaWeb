export function createButton({ label, variant = 'primary', type = 'button', onClick }) {
  const button = document.createElement('button');
  button.type = type;
  button.className = `btn btn-${variant}`;
  button.textContent = label;

  if (typeof onClick === 'function') {
    button.addEventListener('click', onClick);
  }

  return button;
}
