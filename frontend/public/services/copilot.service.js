import { request } from '../api/client.js';

const BASE = '/api/ai';
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
const STORAGE_PREFIX = 'copilot_';

// ============================================================================
// Internal helpers
// ============================================================================

async function requestWithRetry(config) {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      return await request(config);
    } catch (error) {
      if (attempt === MAX_RETRIES - 1) throw error;
      await new Promise((resolve) =>
        setTimeout(resolve, RETRY_DELAY_MS * Math.pow(2, attempt))
      );
    }
  }
}

// ============================================================================
// Auth
// ============================================================================

export async function startCopilotAuth(enterpriseUrl = null) {
  return requestWithRetry({
    method: 'POST',
    url: `${BASE}/authorize`,
    data: { enterprise_url: enterpriseUrl },
  });
}

export async function isCopilotAuthenticated() {
  try {
    const data = await request({ method: 'GET', url: `${BASE}/token/check` });
    return data.authenticated === true;
  } catch {
    return false;
  }
}

export async function pollCopilotAuth(maxAttempts = 60, delayMs = 1000) {
  for (let i = 0; i < maxAttempts; i++) {
    if (await isCopilotAuthenticated()) return true;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return false;
}

// ============================================================================
// Models
// ============================================================================

export async function listCopilotModels() {
  const data = await requestWithRetry({ method: 'GET', url: `${BASE}/models` });
  return data.models;
}

// ============================================================================
// Generation
// ============================================================================

export async function generateContent(prompt, options = {}) {
  return requestWithRetry({
    method: 'POST',
    url: `${BASE}/generate`,
    data: { prompt, ...options },
  });
}

export async function generateRobotTestWithCopilot(prompt, options = {}) {
  return requestWithRetry({
    method: 'POST',
    url: `${BASE}/robot-test`,
    data: { prompt, ...options },
  });
}

// ============================================================================
// Health
// ============================================================================

export async function copilotHealthCheck() {
  try {
    return await request({ method: 'GET', url: `${BASE}/health` });
  } catch (error) {
    return { ok: false, authenticated: false, message: String(error) };
  }
}

// ============================================================================
// Storage
// ============================================================================

export const copilotStorage = {
  getModel: () =>
    localStorage.getItem(`${STORAGE_PREFIX}selected_model`) || 'gpt-4o-mini',
  setModel: (modelId) =>
    localStorage.setItem(`${STORAGE_PREFIX}selected_model`, modelId),
  getLastPrompt: () =>
    localStorage.getItem(`${STORAGE_PREFIX}last_prompt`) || '',
  setLastPrompt: (prompt) =>
    localStorage.setItem(`${STORAGE_PREFIX}last_prompt`, prompt),
  getAuthToken: () =>
    sessionStorage.getItem(`${STORAGE_PREFIX}token`),
  setAuthToken: (token) =>
    sessionStorage.setItem(`${STORAGE_PREFIX}token`, token),
  clearAuth: () =>
    sessionStorage.removeItem(`${STORAGE_PREFIX}token`),
};
