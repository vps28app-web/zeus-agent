const { invoke } = window.__TAURI__.core;

let currentProject = null;
let isProcessing = false;

// Projetos conhecidos
const projects = [
  { name: 'Projeto Atual', path: '.' },
  { name: 'GuiaGps', path: '/home/valdeir/Documentos/Dev/GuiaGps' },
  { name: 'REA', path: '/home/valdeir/Documentos/Dev/REA/recreated-gps-app' },
  { name: 'Zeus', path: '/home/valdeir/Documentos/Dev/Zeus' },
];

function init() {
  renderProjects();
  document.getElementById('input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
  });
}

function renderProjects() {
  const container = document.getElementById('projects');
  container.innerHTML = projects.map(p => `
    <div class="project-item ${currentProject === p.path ? 'active' : ''}"
         onclick="selectProject('${p.path}')">
      ${p.name}
    </div>
  `).join('');
}

function selectProject(path) {
  currentProject = path;
  renderProjects();
  addMessage('system', `Projeto selecionado: ${path}`);
}

async function sendMessage() {
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text || isProcessing) return;

  input.value = '';
  addMessage('user', text);
  setProcessing(true);

  try {
    const response = await invoke('run_zeus', {
      command: text,
      cwd: currentProject || '.',
    });
    addMessage('zeus', response);
  } catch (error) {
    addMessage('error', `Erro: ${error}`);
  } finally {
    setProcessing(false);
  }
}

function addMessage(type, text) {
  const container = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = `message ${type}`;
  div.textContent = text;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function setProcessing(processing) {
  isProcessing = processing;
  const btn = document.getElementById('send');
  const status = document.getElementById('status');
  btn.disabled = processing;
  status.textContent = processing ? 'Processando...' : 'Pronto';
  status.style.color = processing ? '#f39c12' : '#4ecca3';
}

init();
