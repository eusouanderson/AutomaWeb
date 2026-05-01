/**
 * Example: Copilot Integration Frontend Service
 * 
 * Este arquivo demonstra como integrar o Copilot no frontend
 * Adapte para seu framework (React, Vue, Angular, etc)
 */

// ============================================================================
// Services
// ============================================================================

export class CopilotService {
  private baseUrl: string = '/api/ai';

  async startAuthentication(
    enterpriseUrl?: string
  ): Promise<{
    verification_uri: string;
    user_code: string;
    expires_in: number;
  }> {
    const response = await fetch(`${this.baseUrl}/authorize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enterprise_url: enterpriseUrl })
    });

    if (!response.ok) {
      throw new Error(`Authentication failed: ${response.statusText}`);
    }

    return response.json();
  }

  async checkAuthentication(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/token/check`);
      const data = await response.json();
      return data.authenticated === true;
    } catch {
      return false;
    }
  }

  async listModels(): Promise<
    Array<{
      id: string;
      name: string;
      family: string;
      capabilities: Record<string, boolean>;
      limits: Record<string, number>;
    }>
  > {
    const response = await fetch(`${this.baseUrl}/models`);

    if (!response.ok) {
      throw new Error(`Failed to fetch models: ${response.statusText}`);
    }

    const data = await response.json();
    return data.models;
  }

  async generateContent(
    prompt: string,
    options?: {
      model?: string;
      system_prompt?: string;
      temperature?: number;
      max_tokens?: number;
    }
  ): Promise<{ content: string; model: string }> {
    const response = await fetch(`${this.baseUrl}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        ...options
      })
    });

    if (!response.ok) {
      throw new Error(`Generation failed: ${response.statusText}`);
    }

    return response.json();
  }

  async generateRobotTest(
    prompt: string,
    options?: {
      context?: string;
      page_structure?: Record<string, any>;
      model?: string;
    }
  ): Promise<{ test_code: string; model: string }> {
    const response = await fetch(`${this.baseUrl}/robot-test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        ...options
      })
    });

    if (!response.ok) {
      throw new Error(`Test generation failed: ${response.statusText}`);
    }

    return response.json();
  }

  async healthCheck(): Promise<{
    ok: boolean;
    authenticated: boolean;
    message: string;
  }> {
    try {
      const response = await fetch(`${this.baseUrl}/health`);
      return response.json();
    } catch (error) {
      return {
        ok: false,
        authenticated: false,
        message: `Health check failed: ${error}`
      };
    }
  }
}

// ============================================================================
// React Hook Example
// ============================================================================

import { useState, useEffect, useCallback } from 'react';

export function useCopilot() {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const service = new CopilotService();

  const checkAuth = useCallback(async () => {
    try {
      const isAuth = await service.checkAuthentication();
      setAuthenticated(isAuth);
    } catch (err) {
      setError(`Auth check failed: ${err}`);
    }
  }, []);

  const startAuth = useCallback(async () => {
    setLoading(true);
    try {
      const authInfo = await service.startAuthentication();
      return authInfo;
    } catch (err) {
      setError(`Auth failed: ${err}`);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadModels = useCallback(async () => {
    setLoading(true);
    try {
      const availableModels = await service.listModels();
      setModels(availableModels);
    } catch (err) {
      setError(`Failed to load models: ${err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const generateTest = useCallback(
    async (prompt: string, context?: string, structure?: any) => {
      setLoading(true);
      try {
        const result = await service.generateRobotTest(prompt, {
          context,
          page_structure: structure
        });
        setError(null);
        return result;
      } catch (err) {
        setError(`Generation failed: ${err}`);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  return {
    authenticated,
    loading,
    models,
    error,
    checkAuth,
    startAuth,
    loadModels,
    generateTest
  };
}

// ============================================================================
// React Component Example
// ============================================================================

import React from 'react';

export function CopilotTestGenerator() {
  const {
    authenticated,
    loading,
    models,
    error,
    startAuth,
    loadModels,
    generateTest
  } = useCopilot();

  const [selectedModel, setSelectedModel] = React.useState('gpt-5-mini');
  const [prompt, setPrompt] = React.useState('');
  const [generatedCode, setGeneratedCode] = React.useState('');
  const [authMessage, setAuthMessage] = React.useState('');

  const handleAuth = async () => {
    try {
      const authInfo = await startAuth();
      setAuthMessage(
        `✅ Acesse: ${authInfo.verification_uri}\nCódigo: ${authInfo.user_code}`
      );

      // Poll para verificar autenticação
      const checkInterval = setInterval(async () => {
        const isAuth = authenticated;
        if (isAuth) {
          clearInterval(checkInterval);
          setAuthMessage('✅ Autenticado com sucesso!');
          await loadModels();
        }
      }, 3000);
    } catch (err) {
      setAuthMessage(`❌ Erro: ${err}`);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      alert('Por favor, informe um prompt');
      return;
    }

    try {
      const result = await generateTest(prompt);
      setGeneratedCode(result.test_code);
    } catch (err) {
      alert(`Erro ao gerar: ${err}`);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(generatedCode);
    alert('✅ Copiado para área de transferência!');
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>🤖 Gerador de Testes com Copilot</h1>

      {/* Seção de Autenticação */}
      {!authenticated && (
        <div style={{ marginBottom: '20px', padding: '10px', border: '1px solid #ddd' }}>
          <button onClick={handleAuth} disabled={loading}>
            {loading ? '⏳ Autenticando...' : '🔐 Conectar ao Copilot'}
          </button>
          {authMessage && <p>{authMessage}</p>}
        </div>
      )}

      {/* Seção de Seleção de Modelo */}
      {authenticated && models.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <label htmlFor="model-select">📊 Selecione o Modelo:</label>
          <select
            id="model-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.family})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Seção de Geração */}
      {authenticated && (
        <div style={{ marginBottom: '20px' }}>
          <div>
            <label htmlFor="prompt">📝 Descreva o teste:</label>
            <textarea
              id="prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ex: Criar teste de login com email e senha"
              rows={4}
              style={{ width: '100%', fontFamily: 'monospace' }}
            />
          </div>

          <button onClick={handleGenerate} disabled={loading || !prompt.trim()}>
            {loading ? '⏳ Gerando...' : '🚀 Gerar Teste'}
          </button>

          {error && <p style={{ color: 'red' }}>❌ {error}</p>}
        </div>
      )}

      {/* Resultado */}
      {generatedCode && (
        <div
          style={{
            background: '#000',
            color: '#0f0',
            padding: '15px',
            borderRadius: '4px',
            fontFamily: 'monospace',
            marginTop: '20px',
            maxHeight: '400px',
            overflow: 'auto'
          }}
        >
          <pre>{generatedCode}</pre>
          <button onClick={copyToClipboard} style={{ marginTop: '10px' }}>
            📋 Copiar Código
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Vue 3 Composition API Example
// ============================================================================

/*
<template>
  <div class="copilot-panel">
    <!-- Auth Section -->
    <div v-if="!authenticated" class="auth-section">
      <button @click="handleAuth" :disabled="loading">
        🔐 Conectar ao Copilot
      </button>
      <p v-if="authMessage" class="message">{{ authMessage }}</p>
    </div>

    <!-- Models Selection -->
    <div v-if="authenticated && models.length > 0" class="models-section">
      <label for="model-select">📊 Modelo:</label>
      <select v-model="selectedModel" id="model-select">
        <option v-for="m in models" :key="m.id" :value="m.id">
          {{ m.name }} ({{ m.family }})
        </option>
      </select>
    </div>

    <!-- Test Generation -->
    <div v-if="authenticated" class="generation-section">
      <label for="prompt">📝 Prompt:</label>
      <textarea
        v-model="prompt"
        id="prompt"
        placeholder="Descrever teste..."
        rows="4"
      />

      <button @click="handleGenerate" :disabled="loading || !prompt.trim()">
        {{ loading ? '⏳ Gerando...' : '🚀 Gerar Teste' }}
      </button>

      <p v-if="error" class="error">❌ {{ error }}</p>
    </div>

    <!-- Result -->
    <div v-if="generatedCode" class="result">
      <pre>{{ generatedCode }}</pre>
      <button @click="copyToClipboard">📋 Copiar</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const authenticated = ref(false);
const loading = ref(false);
const models = ref([]);
const selectedModel = ref('gpt-5-mini');
const prompt = ref('');
const generatedCode = ref('');
const authMessage = ref('');
const error = ref('');

const service = new CopilotService();

const handleAuth = async () => {
  try {
    const authInfo = await service.startAuthentication();
    authMessage.value = `Acesse: ${authInfo.verification_uri} Código: ${authInfo.user_code}`;
    
    const interval = setInterval(async () => {
      const isAuth = await service.checkAuthentication();
      if (isAuth) {
        clearInterval(interval);
        authenticated.value = true;
        await loadModels();
      }
    }, 3000);
  } catch (err) {
    error.value = String(err);
  }
};

const loadModels = async () => {
  try {
    models.value = await service.listModels();
  } catch (err) {
    error.value = String(err);
  }
};

const handleGenerate = async () => {
  try {
    const result = await service.generateRobotTest(prompt.value);
    generatedCode.value = result.test_code;
  } catch (err) {
    error.value = String(err);
  }
};

const copyToClipboard = async () => {
  await navigator.clipboard.writeText(generatedCode.value);
  alert('✅ Copiado!');
};

onMounted(async () => {
  authenticated.value = await service.checkAuthentication();
  if (authenticated.value) {
    await loadModels();
  }
});
</script>
*/

// ============================================================================
// Error Handling Helper
// ============================================================================

export class CopilotError extends Error {
  constructor(
    public code: string,
    public statusCode?: number,
    message?: string
  ) {
    super(message || code);
    this.name = 'CopilotError';
  }
}

export function handleCopilotError(error: unknown): string {
  if (error instanceof CopilotError) {
    switch (error.code) {
      case 'AUTH_FAILED':
        return 'Falha na autenticação. Tente novamente.';
      case 'MODELS_FETCH_FAILED':
        return 'Não foi possível buscar modelos.';
      case 'GENERATION_FAILED':
        return 'Falha ao gerar teste. Tente com um prompt menor.';
      case 'PAYLOAD_TOO_LARGE':
        return 'Payload muito grande. Reduza a complexidade.';
      default:
        return error.message || 'Erro desconhecido';
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

// ============================================================================
// Local Storage Helper
// ============================================================================

export class CopilotStorage {
  private static PREFIX = 'copilot_';

  static setModel(modelId: string): void {
    localStorage.setItem(`${this.PREFIX}selected_model`, modelId);
  }

  static getModel(): string {
    return localStorage.getItem(`${this.PREFIX}selected_model`) || 'gpt-5-mini';
  }

  static setLastPrompt(prompt: string): void {
    localStorage.setItem(`${this.PREFIX}last_prompt`, prompt);
  }

  static getLastPrompt(): string {
    return localStorage.getItem(`${this.PREFIX}last_prompt`) || '';
  }

  static setAuthToken(token: string): void {
    sessionStorage.setItem(`${this.PREFIX}token`, token);
  }

  static getAuthToken(): string | null {
    return sessionStorage.getItem(`${this.PREFIX}token`);
  }

  static clearAuth(): void {
    sessionStorage.removeItem(`${this.PREFIX}token`);
  }
}

// ============================================================================
// Export All
// ============================================================================

export * from './types'; // Se tiver arquivo de tipos
