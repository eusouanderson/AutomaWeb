/**
 * Copilot Authentication Manager
 * Handles OAuth Device Code Flow in the browser
 */

export class CopilotAuthManager {
  constructor() {
    this.apiBase = '/api/ai';
    this.pollInterval = 5000;
    this.maxPollAttempts = 200;
  }

  async checkAuthentication() {
    try {
      const response = await axios.get(`${this.apiBase}/token/check`);
      return response.data.authenticated;
    } catch (error) {
      console.error('Auth check failed:', error);
      return false;
    }
  }

  async startAuthorization() {
    try {
      const response = await axios.post(`${this.apiBase}/authorize`, {
        enterprise_url: null
      });

      return {
        success: true,
        verification_uri: response.data.verification_uri,
        user_code: response.data.user_code,
        device_code: response.data.device_code,
        expires_in: response.data.expires_in
      };
    } catch (error) {
      console.error('Authorization start failed:', error);
      return {
        success: false,
        error: error.response?.data?.detail || error.message
      };
    }
  }

  async pollDeviceCode(deviceCode, onProgress) {
    let attempts = 0;
    let currentInterval = this.pollInterval;

    return new Promise((resolve, reject) => {
      const pollFn = async () => {
        attempts++;

        if (attempts > this.maxPollAttempts) {
          reject(new Error('Authorization timeout'));
          return;
        }

        try {
          const response = await axios.post(`${this.apiBase}/authorize/poll`, {
            device_code: deviceCode
          });

          if (onProgress) {
            onProgress({
              authenticated: response.data.authenticated,
              message: response.data.message,
              progress: (attempts / this.maxPollAttempts) * 100
            });
          }

          if (response.data.authenticated) {
            resolve({
              success: true,
              message: response.data.message
            });
            return;
          }

          if (response.data.slow_down) {
            currentInterval = Math.min(currentInterval + 5000, 30000);
          }

          setTimeout(pollFn, currentInterval);
        } catch (error) {
          console.error('Poll failed:', error);
          reject(error);
        }
      };

      pollFn();
    });
  }

  async authorize(onProgress) {
    const authResult = await this.startAuthorization();
    if (!authResult.success) {
      throw new Error(authResult.error);
    }

    window.open(authResult.verification_uri, '_blank', 'width=500,height=700');
    return this.pollDeviceCode(authResult.device_code, onProgress);
  }
}

export class AuthorizationUI {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.authManager = new CopilotAuthManager();
  }

  async showAuthDialog() {
    console.log('📋 showAuthDialog called');
    console.log('Container:', this.container);
    
    return new Promise((resolve, reject) => {
      this.authManager.startAuthorization().then(authResult => {
        console.log('📋 startAuthorization result:', authResult);
        
        if (!authResult.success) {
          reject(new Error(authResult.error));
          return;
        }

        const modal = document.createElement('div');
        modal.className = 'auth-modal';
        modal.innerHTML = `
          <div class="auth-modal-content">
            <div class="auth-modal-header">
              <h2>🔐 Authorize Copilot</h2>
              <button class="auth-modal-close">&times;</button>
            </div>
            
            <div class="auth-modal-body">
              <div class="auth-instructions">
                <strong>Para autorizar, siga estes passos:</strong>
                <ol style="margin: 10px 0; padding-left: 20px;">
                  <li>Clique no botão abaixo ou visite: <a href="${authResult.verification_uri}" target="_blank" style="color: #667eea; font-weight: 600;">${authResult.verification_uri}</a></li>
                  <li>Digite ou copie o código:</li>
                  <li>Faça login com sua conta GitHub</li>
                  <li>Autorize a aplicação</li>
                </ol>
              </div>

              <div class="auth-device-code">
                <div class="auth-device-code-label">Código do Dispositivo:</div>
                <div class="auth-device-code-value" id="device-code-value">${authResult.user_code}</div>
                <button class="btn-copy" id="copy-code-btn" style="
                  background: #f0f0f0;
                  border: none;
                  padding: 8px 12px;
                  border-radius: 4px;
                  cursor: pointer;
                  font-size: 12px;
                  margin-top: 10px;
                  transition: all 0.2s;
                ">📋 Copiar Código</button>
              </div>

              <div style="text-align: center; margin: 20px 0;">
                <button id="auth-github-btn" class="auth-modal-btn-primary">
                  ✓ Abrir GitHub para Autorizar
                </button>
              </div>

              <p style="font-size: 13px; color: #999; text-align: center; margin-top: 15px;">
                Uma janela será aberta. Após autorizar, retorne aqui.
              </p>
            </div>

            <div id="auth-progress" style="display:none; padding: 20px 30px; border-top: 1px solid #eee;">
              <div class="progress-bar" style="
                width: 100%;
                height: 4px;
                background: #eee;
                border-radius: 4px;
                overflow: hidden;
                margin-bottom: 15px;
              ">
                <div id="auth-progress-fill" style="
                  height: 100%;
                  background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                  width: 0%;
                  transition: width 0.3s ease;
                "></div>
              </div>
              <p id="auth-status-msg" style="
                font-size: 14px;
                color: #666;
                text-align: center;
                margin: 0;
                min-height: 24px;
                line-height: 1.5;
              ">⏳ Aguardando autorização...</p>
            </div>
          </div>
        `;

        console.log('📋 Modal created. Adding to container...');
        this.container.appendChild(modal);
        console.log('✓ Modal added to DOM');

        document.getElementById('copy-code-btn').addEventListener('click', () => {
          const codeValue = authResult.user_code;
          navigator.clipboard.writeText(codeValue).then(() => {
            const btn = document.getElementById('copy-code-btn');
            btn.textContent = '✓ Copiado!';
            setTimeout(() => {
              btn.textContent = '📋 Copiar Código';
            }, 2000);
          });
        });

        document.getElementById('auth-github-btn').addEventListener('click', (e) => {
          e.preventDefault();
          window.open(authResult.verification_uri, '_blank', 'width=500,height=700');
          setTimeout(() => {
            document.querySelector('.auth-modal-body').style.display = 'none';
            document.getElementById('auth-progress').style.display = 'block';

            // Check if already authenticated (e.g. user authorized in another tab)
            const checkAlreadyAuthed = async () => {
              const alreadyAuthed = await this.authManager.checkAuthentication();
              if (alreadyAuthed) {
                modal.remove();
                resolve(true);
                return;
              }
            };

            checkAlreadyAuthed();

            this.authManager.pollDeviceCode(authResult.device_code, (progress) => {
              const fill = document.getElementById('auth-progress-fill');
              fill.style.width = progress.progress + '%';
              document.getElementById('auth-status-msg').textContent = progress.message;
            }).then(() => {
              modal.remove();
              resolve(true);
            }).catch(error => {
              document.getElementById('auth-status-msg').textContent = `❌ Erro: ${error.message}`;
              reject(error);
            });
          }, 500);
        });

        document.querySelector('.auth-modal-close').addEventListener('click', () => {
          modal.remove();
          reject(new Error('Authorization cancelled'));
        });

        modal.addEventListener('click', (e) => {
          if (e.target === modal) {
            modal.remove();
            reject(new Error('Authorization cancelled'));
          }
        });
      });
    });
  }

  async ensureAuthenticated() {
    const isAuthenticated = await this.authManager.checkAuthentication();

    if (!isAuthenticated) {
      try {
        await this.showAuthDialog();
        return true;
      } catch (error) {
        console.error('Authentication required:', error);
        return false;
      }
    }

    return true;
  }
}
