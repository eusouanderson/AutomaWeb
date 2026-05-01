/**
 * Copilot Integration Frontend Service
 * 
 * Este arquivo fornece uma classe TypeScript para integrar Copilot no frontend
 */

// ============================================================================
// Types
// ============================================================================

export interface Model {
  id: string;
  name: string;
  family: string;
  capabilities: {
    reasoning: boolean;
    vision: boolean;
    streaming: boolean;
    tool_calls: boolean;
    structured_outputs: boolean;
  };
  limits: {
    context_tokens: number;
    output_tokens: number;
    prompt_tokens: number;
  };
}

export interface AuthorizationResponse {
  verification_uri: string;
  user_code: string;
  device_code: string;
  expires_in: number;
}

export interface TokenCheckResponse {
  ok: boolean;
  authenticated: boolean;
  message: string;
}

export interface GenerateResponse {
  content: string;
  model: string;
  status: string;
}

export interface RobotTestResponse {
  test_code: string;
  model: string;
  status: string;
}

export interface HealthCheckResponse {
  ok: boolean;
  authenticated: boolean;
  model: string;
  message: string;
}

// ============================================================================
// Main Service
// ============================================================================

export class CopilotService {
  private baseUrl: string = '/api/ai';
  private maxRetries: number = 3;
  private retryDelay: number = 1000;

  /**
   * Start OAuth Device Code Flow
   */
  async startAuthentication(
    enterpriseUrl?: string
  ): Promise<AuthorizationResponse> {
    const response = await this.request<AuthorizationResponse>(
      'POST',
      '/authorize',
      { enterprise_url: enterpriseUrl }
    );
    return response;
  }

  /**
   * Check if user is authenticated
   */
  async checkAuthentication(): Promise<boolean> {
    try {
      const response = await this.request<TokenCheckResponse>(
        'GET',
        '/token/check'
      );
      return response.authenticated === true;
    } catch {
      return false;
    }
  }

  /**
   * Fetch available models
   */
  async listModels(): Promise<Model[]> {
    const response = await this.request<{ models: Model[] }>(
      'GET',
      '/models'
    );
    return response.models;
  }

  /**
   * Generate content with Copilot
   */
  async generateContent(
    prompt: string,
    options?: {
      model?: string;
      system_prompt?: string;
      temperature?: number;
      max_tokens?: number;
    }
  ): Promise<GenerateResponse> {
    return this.request<GenerateResponse>('POST', '/generate', {
      prompt,
      ...options
    });
  }

  /**
   * Generate Robot Framework test code
   */
  async generateRobotTest(
    prompt: string,
    options?: {
      context?: string;
      page_structure?: Record<string, any>;
      model?: string;
    }
  ): Promise<RobotTestResponse> {
    return this.request<RobotTestResponse>('POST', '/robot-test', {
      prompt,
      ...options
    });
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<HealthCheckResponse> {
    try {
      return await this.request<HealthCheckResponse>('GET', '/health');
    } catch (error) {
      return {
        ok: false,
        authenticated: false,
        model: 'gpt-5-mini',
        message: `Health check failed: ${error}`
      };
    }
  }

  /**
   * Internal request method with retry logic
   */
  private async request<T>(
    method: string,
    endpoint: string,
    data?: any
  ): Promise<T> {
    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const options: RequestInit = {
          method,
          headers: { 'Content-Type': 'application/json' }
        };

        if (data && (method === 'POST' || method === 'PUT')) {
          options.body = JSON.stringify(data);
        }

        const response = await fetch(`${this.baseUrl}${endpoint}`, options);

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(
            errorData.detail ||
              `HTTP ${response.status}: ${response.statusText}`
          );
        }

        return response.json();
      } catch (error) {
        if (attempt === this.maxRetries - 1) {
          throw error;
        }

        // Exponential backoff
        await new Promise((resolve) =>
          setTimeout(resolve, this.retryDelay * Math.pow(2, attempt))
        );
      }
    }

    throw new Error('Max retries exceeded');
  }
}

// ============================================================================
// React Hooks
// ============================================================================

// Para usar em React, importe como:
// import { useCopilot } from './copilotService';
//
// Em seu componente:
// const { authenticated, generate } = useCopilot();

export function createCopilotHook(ReactModule: any) {
  const { useState, useEffect, useCallback } = ReactModule;

  return function useCopilot() {
    const [authenticated, setAuthenticated] = useState(false);
    const [loading, setLoading] = useState(false);
    const [models, setModels] = useState<Model[]>([]);
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
  };
}

// ============================================================================
// Storage Helper
// ============================================================================

export class CopilotStorage {
  private static PREFIX = 'copilot_';

  static setModel(modelId: string): void {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(`${this.PREFIX}selected_model`, modelId);
    }
  }

  static getModel(): string {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem(`${this.PREFIX}selected_model`) || 'gpt-5-mini';
    }
    return 'gpt-5-mini';
  }

  static setLastPrompt(prompt: string): void {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(`${this.PREFIX}last_prompt`, prompt);
    }
  }

  static getLastPrompt(): string {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem(`${this.PREFIX}last_prompt`) || '';
    }
    return '';
  }

  static setAuthToken(token: string): void {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(`${this.PREFIX}token`, token);
    }
  }

  static getAuthToken(): string | null {
    if (typeof sessionStorage !== 'undefined') {
      return sessionStorage.getItem(`${this.PREFIX}token`);
    }
    return null;
  }

  static clearAuth(): void {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.removeItem(`${this.PREFIX}token`);
    }
  }
}

// ============================================================================
// Error Handler
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
// Polling Helper
// ============================================================================

export async function pollAuthentication(
  maxAttempts: number = 60,
  delayMs: number = 1000
): Promise<boolean> {
  const service = new CopilotService();

  for (let i = 0; i < maxAttempts; i++) {
    const isAuth = await service.checkAuthentication();
    if (isAuth) {
      return true;
    }

    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  return false;
}

// ============================================================================
// Export Service Instance
// ============================================================================

export const copilotService = new CopilotService();
