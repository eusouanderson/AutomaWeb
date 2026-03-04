// API Base URL
const API_URL = '';

// Utility: Show Toast
function showToast(message, type = 'success') {
    Toastify({
        text: message,
        duration: 3000,
        gravity: 'top',
        position: 'right',
        backgroundColor: type === 'success' ? '#10b981' : '#ef4444',
    }).showToast();
}

// Utility: Format Date
function formatDate(dateString) {
    return new Date(dateString).toLocaleString('pt-BR');
}

// Tab Navigation
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.dataset.tab;
        
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        btn.classList.add('active');
        document.getElementById(`${tabName}-tab`).classList.add('active');
        
        if (tabName === 'projects') loadProjects();
        if (tabName === 'generate') loadProjectsDropdown();
    });
});

// Create Project
document.getElementById('create-project-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const name = document.getElementById('project-name').value;
    const description = document.getElementById('project-description').value;
    
    try {
        await axios.post(`${API_URL}/projects`, { name, description });
        showToast('Projeto criado com sucesso!');
        e.target.reset();
        loadProjects();
    } catch (error) {
        showToast(error.response?.data?.detail || 'Erro ao criar projeto', 'error');
    }
});

// Load Projects
async function loadProjects() {
    const list = document.getElementById('projects-list');
    list.innerHTML = '<div class="loading">Carregando projetos...</div>';
    
    try {
        const { data } = await axios.get(`${API_URL}/projects`);
        
        if (data.length === 0) {
            list.innerHTML = '<div class="empty">Nenhum projeto criado ainda</div>';
            return;
        }
        
        list.innerHTML = data.map(project => `
            <div class="list-item">
                <h3>${project.name}</h3>
                <p>${project.description || 'Sem descrição'}</p>
                <small>ID: ${project.id} | Criado em: ${formatDate(project.created_at)}</small>
            </div>
        `).join('');
    } catch (error) {
        list.innerHTML = '<div class="empty">Erro ao carregar projetos</div>';
        showToast('Erro ao carregar projetos', 'error');
    }
}

// Load Projects Dropdown
async function loadProjectsDropdown() {
    const select = document.getElementById('test-project');
    
    try {
        const { data } = await axios.get(`${API_URL}/projects`);
        
        select.innerHTML = '<option value="">Selecione um projeto</option>' +
            data.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
    } catch (error) {
        showToast('Erro ao carregar projetos', 'error');
    }
}

// Generate Test
document.getElementById('generate-test-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const projectId = parseInt(document.getElementById('test-project').value);
    const prompt = document.getElementById('test-prompt').value;
    const context = document.getElementById('test-context').value;
    
    const resultSection = document.getElementById('generated-result');
    const codeElement = document.getElementById('test-code');
    
    resultSection.classList.add('hidden');
    
    try {
        showToast('Gerando teste... Aguarde.', 'success');
        
        const { data } = await axios.post(`${API_URL}/tests/generate`, {
            project_id: projectId,
            prompt,
            context: context || null
        });
        
        codeElement.textContent = data.content;
        resultSection.classList.remove('hidden');
        
        // Store test ID for download
        document.getElementById('download-test-btn').dataset.testId = data.id;
        
        showToast('Teste gerado com sucesso!');
    } catch (error) {
        showToast(error.response?.data?.detail || 'Erro ao gerar teste', 'error');
    }
});

// Copy Test Code
document.getElementById('copy-test-btn').addEventListener('click', () => {
    const code = document.getElementById('test-code').textContent;
    navigator.clipboard.writeText(code);
    showToast('Código copiado!');
});

// Download Test
document.getElementById('download-test-btn').addEventListener('click', () => {
    const testId = document.getElementById('download-test-btn').dataset.testId;
    window.open(`${API_URL}/tests/${testId}/download`, '_blank');
});

// Initial Load
loadProjects();
