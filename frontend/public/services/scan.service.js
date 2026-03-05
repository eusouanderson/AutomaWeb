import { scanProject } from '../api/automaweb.api.js';
import { isValidUrl } from '../utils/validators.js';

export async function runProjectScan(projectUrl, handlers = {}) {
  if (!isValidUrl(projectUrl)) {
    throw new Error('A valid project URL is required to scan');
  }

  let scanResult = null;
  await scanProject(projectUrl, (message) => {
    if (message.type === 'progress') {
      handlers.onProgress?.(message.message);
      return;
    }

    if (message.type === 'result') {
      scanResult = message.data;
      handlers.onResult?.(message.data);
      return;
    }

    if (message.type === 'error') {
      handlers.onError?.(message.message);
    }
  });

  return scanResult;
}
