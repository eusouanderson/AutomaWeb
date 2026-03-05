export function createLoader(label = 'Loading...') {
  const wrapper = document.createElement('div');
  wrapper.className = 'loader';
  wrapper.innerHTML = `<span class="loader-dot" aria-hidden="true"></span><span>${label}</span>`;
  return wrapper;
}
