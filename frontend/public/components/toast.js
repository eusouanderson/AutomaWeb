export function toast(message, type = 'success') {
  const palette = {
    success: '#0f766e',
    error: '#b91c1c',
    info: '#1d4ed8'
  };

  globalThis
    .Toastify({
      text: message,
      duration: 3000,
      gravity: 'top',
      position: 'right',
      backgroundColor: palette[type] || palette.info
    })
    .showToast();
}
