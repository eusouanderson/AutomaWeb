const API_BASE_URL = '';

const axios = globalThis.axios;

if (!axios) {
  throw new Error('Axios global not found. Ensure axios script is loaded before app.js');
}

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    const message = detail || error.message || 'Unexpected API error';
    const normalized = new Error(message);
    normalized.status = error.response?.status || 500;
    normalized.data = error.response?.data || null;
    throw normalized;
  }
);

export async function request(config) {
  const response = await http.request(config);
  return response.data;
}

export async function streamPost(path, payload, onMessage) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok || !response.body) {
    throw new Error('Could not start stream request');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    events.forEach((eventBlock) => {
      const line = eventBlock.split('\n').find((item) => item.startsWith('data: '));
      if (!line) {
        return;
      }
      const message = JSON.parse(line.slice(6));
      onMessage(message);
    });
  }
}

export { http };
