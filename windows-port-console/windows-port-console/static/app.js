/* ─── Windows Port Console — Frontend ──────────────────────────── */

// ─── State ─────────────────────────────────────────────────────
const state = {
  currentView: 'dashboard',
  currentFile: 'untitled.cpp',
  currentFilePath: '',
  files: [],
  vmRunning: false,
  terminalWs: null,
  terminalMode: 'linux', // 'linux' or 'winrm'
  settings: {
    username: localStorage.getItem('winrm_username') || '',
    password: localStorage.getItem('winrm_password') || '',
    host: localStorage.getItem('winrm_host') || 'localhost',
    port: parseInt(localStorage.getItem('winrm_port') || '5985'),
  },
};

// ─── Navigation ────────────────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const view = btn.dataset.view;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById(`view-${view}`).classList.add('active');
    state.currentView = view;
    if (view === 'dashboard') refreshDashboard();
    if (view === 'files') refreshFiles();
    if (view === 'code-editor') refreshFileTree();
  });
});

// ─── Dashboard ──────────────────────────────────────────────────
async function refreshDashboard() {
  try {
    const r = await fetch('/api/vm/status');
    const data = await r.json();
    updateVmStatus(data);
  } catch (e) {
    console.error('Dashboard refresh failed:', e);
  }
}

function updateVmStatus(data) {
  const stateEl = document.getElementById('card-state');
  const specsEl = document.getElementById('card-specs');
  const ipEl = document.getElementById('card-ip');
  const isoEl = document.getElementById('card-iso');
  const indicator = document.getElementById('vm-status-indicator');
  const statusText = document.getElementById('vm-status-text');

  const vmState = data.state || 'unknown';
  stateEl.textContent = vmState;

  if (data.memory && data.cpus) {
    specsEl.textContent = `${data.memory} MB / ${data.cpus} CPUs`;
  } else {
    specsEl.textContent = data.vbox_installed ? 'VM not created' : 'VBox not installed';
  }

  ipEl.textContent = data.ip || '—';

  if (data.iso) {
    isoEl.textContent = data.iso.exists ? `${data.iso.size_gb} GB ✓` : 'Not found';
  }

  // Sidebar indicator
  if (vmState === 'running') {
    indicator.className = 'status-dot online';
    statusText.textContent = 'VM Running';
    state.vmRunning = true;
  } else if (vmState === 'not_created') {
    indicator.className = 'status-dot offline';
    statusText.textContent = 'VM Not Created';
    state.vmRunning = false;
  } else if (vmState === 'stopped' || vmState === 'saved' || vmState === 'aborted') {
    indicator.className = 'status-dot offline';
    statusText.textContent = 'VM Stopped';
    state.vmRunning = false;
  } else {
    indicator.className = 'status-dot busy';
    statusText.textContent = vmState;
    state.vmRunning = false;
  }
}

// VM Controls
document.getElementById('vm-start').addEventListener('click', async () => {
  await fetch('/api/vm/start?headless=true', { method: 'POST' });
  setTimeout(refreshDashboard, 2000);
});

document.getElementById('vm-start-gui').addEventListener('click', async () => {
  await fetch('/api/vm/start?headless=false', { method: 'POST' });
  setTimeout(refreshDashboard, 2000);
});

document.getElementById('vm-stop').addEventListener('click', async () => {
  await fetch('/api/vm/stop', { method: 'POST' });
  setTimeout(refreshDashboard, 5000);
});

document.getElementById('vm-poweroff').addEventListener('click', async () => {
  await fetch('/api/vm/stop?force=true', { method: 'POST' });
  setTimeout(refreshDashboard, 2000);
});

document.getElementById('vm-create').addEventListener('click', async () => {
  const r = await fetch('/api/vm/create', { method: 'POST' });
  const data = await r.json();
  if (data.success) {
    alert('VM created successfully!');
  } else {
    alert('Error: ' + (data.error || data.errors?.join('\n') || 'Unknown'));
  }
  refreshDashboard();
});

document.getElementById('vm-screenshot').addEventListener('click', async () => {
  const img = document.getElementById('screenshot-img');
  const placeholder = document.getElementById('screenshot-placeholder');
  img.style.display = 'none';
  placeholder.style.display = 'block';
  placeholder.textContent = 'Capturing screenshot...';

  // Fetch the screenshot
  const r = await fetch('/api/vm/screenshot', { method: 'POST' });
  if (r.ok) {
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    img.src = url;
    img.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    const err = await r.json();
    placeholder.textContent = 'Error: ' + (err.error || 'VM not running');
  }
});

document.getElementById('refresh-status').addEventListener('click', refreshDashboard);

// Initial dashboard load
refreshDashboard();

// ─── Code Editor ────────────────────────────────────────────────
const editor = document.getElementById('code-editor');

// Track cursor position
editor.addEventListener('click', updateCursorPos);
editor.addEventListener('keyup', updateCursorPos);

function updateCursorPos() {
  const pos = editor.selectionStart;
  const text = editor.value.substring(0, pos);
  const lines = text.split('\n');
  const line = lines.length;
  const col = lines[lines.length - 1].length + 1;
  document.getElementById('cursor-position').textContent = `Ln ${line}, Col ${col}`;
}

// File tree
async function refreshFileTree() {
  const tree = document.getElementById('file-tree');
  tree.innerHTML = '<div class="file-item loading">Loading...</div>';

  try {
    const r = await fetch('/api/files/list');
    const data = await r.json();
    state.files = data.files || [];
    renderFileTree(data.files || []);
  } catch (e) {
    tree.innerHTML = '<div class="file-item">Error loading files</div>';
  }
}

function renderFileTree(files) {
  const tree = document.getElementById('file-tree');
  tree.innerHTML = '';
  files.forEach(f => {
    const div = document.createElement('div');
    div.className = `file-item${f.is_dir ? ' dir' : ''}`;
    div.textContent = (f.is_dir ? '📁 ' : '📄 ') + f.name;
    div.addEventListener('click', () => {
      if (f.is_dir) return;
      openFile(f.path);
    });
    tree.appendChild(div);
  });
}

async function openFile(path) {
  try {
    const r = await fetch(`/api/files/read?path=${encodeURIComponent(path)}`);
    if (!r.ok) return;
    const data = await r.json();
    editor.value = data.content;
    state.currentFilePath = path;
    state.currentFile = path.split('/').pop() || path;
    updateCursorPos();
    updateEditorTab(state.currentFile);
    // Auto-detect language from extension
    const ext = state.currentFile.split('.').pop();
    const langMap = { 'py': 'Python', 'js': 'JavaScript', 'ts': 'TypeScript',
      'cpp': 'C++', 'c': 'C', 'h': 'C Header', 'hpp': 'C++ Header',
      'cs': 'C#', 'java': 'Java', 'rs': 'Rust', 'go': 'Go',
      'sh': 'Bash', 'ps1': 'PowerShell', 'bat': 'Batch',
      'html': 'HTML', 'css': 'CSS', 'json': 'JSON', 'xml': 'XML',
      'yaml': 'YAML', 'yml': 'YAML', 'md': 'Markdown',
      'txt': 'Text', 'lua': 'Lua' };
    document.getElementById('file-language').textContent = langMap[ext] || ext.toUpperCase();
  } catch (e) {
    console.error('Open file failed:', e);
  }
}

function updateEditorTab(filename) {
  const container = document.getElementById('editor-tabs');
  container.innerHTML = `<div class="tab active" data-file="${filename}">${filename}</div>`;
}

// Editor actions
document.getElementById('editor-new').addEventListener('click', () => {
  editor.value = '';
  state.currentFilePath = '';
  state.currentFile = 'untitled.cpp';
  updateEditorTab('untitled.cpp');
  document.getElementById('file-language').textContent = 'C++';
});

document.getElementById('editor-save').addEventListener('click', async () => {
  const path = state.currentFilePath || state.currentFile;
  try {
    const r = await fetch('/api/files/write', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ path, content: editor.value }),
    });
    const data = await r.json();
    if (data.success) {
      // Show save notification
      const statusbar = document.getElementById('editor-statusbar');
      const saved = document.createElement('span');
      saved.textContent = '✓ Saved';
      saved.style.color = 'var(--green)';
      statusbar.appendChild(saved);
      setTimeout(() => saved.remove(), 2000);
      refreshFileTree();
    }
  } catch (e) {
    alert('Save failed: ' + e);
  }
});

document.getElementById('editor-analyze').addEventListener('click', async () => {
  const ext = state.currentFile.split('.').pop();
  try {
    const r = await fetch('/api/ai/port', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: editor.value,
        source_lang: state.currentFile,
        target_lang: 'linux',
      }),
    });
    const data = await r.json();
    showAnalysis(data);
  } catch (e) {
    alert('Analysis failed: ' + e);
  }
});

document.getElementById('editor-send-to-vm').addEventListener('click', async () => {
  if (!state.vmRunning) {
    alert('VM is not running. Start it first from the Dashboard.');
    return;
  }
  const path = state.currentFilePath || state.currentFile;
  try {
    const r = await fetch('/api/files/write', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ path, content: editor.value }),
    });
    const data = await r.json();
    if (data.success) {
      alert(`File saved to shared folder. Access it in the VM at Z:\\${path}`);
    }
  } catch (e) {
    alert('Send failed: ' + e);
  }
});

// ─── Analysis Display ───────────────────────────────────────────
function showAnalysis(data) {
  const panel = document.getElementById('analysis-results');
  panel.innerHTML = '';

  // Score
  const score = data.portability_score ?? 50;
  const scoreClass = score >= 70 ? 'score-high' : score >= 40 ? 'score-medium' : 'score-low';
  const scoreDiv = document.createElement('div');
  scoreDiv.className = 'port-score';
  scoreDiv.innerHTML = `
    <div class="score-value ${scoreClass}">${score}</div>
    <div class="score-label">Portability Score</div>
  `;
  panel.appendChild(scoreDiv);

  // Windows patterns
  if (data.windows_patterns && data.windows_patterns.length > 0) {
    const section = document.createElement('div');
    section.className = 'analysis-section';
    section.innerHTML = `<h4>⚠ Windows Patterns Found (${data.windows_patterns.length})</h4>`;
    data.windows_patterns.forEach(p => {
      const item = document.createElement('div');
      item.className = 'analysis-item';
      item.innerHTML = `<span class="issue-badge win">WIN</span> ${p.description}`;
      if (p.occurrences && p.occurrences.length > 0) {
        const locs = p.occurrences.map(o => `L${o.line}`).join(', ');
        item.innerHTML += `<br><small style="color:var(--text-secondary);margin-left:50px;">At: ${locs}</small>`;
      }
      section.appendChild(item);
    });
    panel.appendChild(section);
  }

  // Suggestions
  if (data.suggestions && data.suggestions.length > 0) {
    const section = document.createElement('div');
    section.className = 'analysis-section';
    section.innerHTML = `<h4>💡 Porting Suggestions</h4>`;
    data.suggestions.forEach(s => {
      const item = document.createElement('div');
      item.className = 'analysis-item';
      item.innerHTML = `<strong>${s.category}:</strong><br>`;
      s.items.forEach(i => {
        item.innerHTML += `<span style="color:var(--text-secondary);font-size:12px;">  • ${i}</span><br>`;
      });
      section.appendChild(item);
    });
    panel.appendChild(section);
  }

  if ((!data.windows_patterns || data.windows_patterns.length === 0) &&
      (!data.suggestions || data.suggestions.length === 0)) {
    panel.innerHTML = '<div class="analysis-empty">No Windows-specific patterns found. Code appears portable.</div>';
  }

  // Switch to AI Assistant view
  document.querySelector('.nav-btn[data-view="ai-assistant"]').click();
}

// ─── Terminal ──────────────────────────────────────────────────
const terminalInput = document.getElementById('terminal-input');
const terminalOutput = document.getElementById('terminal-output');
const terminalPrompt = document.getElementById('terminal-prompt');
const terminalMode = document.getElementById('terminal-mode');

let terminalWs = null;
let commandHistory = [];
let historyIndex = -1;

function connectTerminal() {
  if (terminalWs) {
    terminalWs.close();
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/terminal`;
  terminalWs = new WebSocket(wsUrl);

  terminalWs.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'banner') {
      terminalOutput.textContent += msg.message + '\n';
      terminalPrompt.textContent = msg.prompt;
    } else if (msg.type === 'output') {
      terminalOutput.textContent += msg.data;
      if (!msg.data.endsWith('\n')) terminalOutput.textContent += '\n';
      terminalPrompt.textContent = `${getUser()}@host:~$ `;
      terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }
  };

  terminalWs.onclose = () => {
    terminalOutput.textContent += '\n[Terminal disconnected]\n';
    terminalWs = null;
  };

  terminalWs.onerror = () => {
    terminalOutput.textContent += '\n[Terminal error — reconnecting...]\n';
    setTimeout(connectTerminal, 3000);
  };
}

function getUser() {
  return 'developer';
}

terminalInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const cmd = terminalInput.value;
    terminalInput.value = '';

    if (cmd.trim()) {
      commandHistory.push(cmd);
      historyIndex = commandHistory.length;

      if (terminalWs && terminalWs.readyState === WebSocket.OPEN) {
        terminalWs.send(JSON.stringify({ type: 'command', command: cmd }));
        terminalOutput.textContent += `${terminalPrompt.textContent}${cmd}\n`;
      } else {
        terminalOutput.textContent += `${terminalPrompt.textContent}${cmd}\n[Terminal not connected — restarting...]\n`;
        connectTerminal();
      }
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (historyIndex > 0) {
      historyIndex--;
      terminalInput.value = commandHistory[historyIndex];
    }
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (historyIndex < commandHistory.length - 1) {
      historyIndex++;
      terminalInput.value = commandHistory[historyIndex];
    } else {
      historyIndex = commandHistory.length;
      terminalInput.value = '';
    }
  }
});

document.getElementById('terminal-clear').addEventListener('click', () => {
  terminalOutput.textContent = '';
});

document.getElementById('terminal-clear').addEventListener('click', () => {
  terminalOutput.textContent = '';
});

// ─── Files ──────────────────────────────────────────────────────
async function refreshFiles(dir = '.') {
  const list = document.getElementById('file-list');
  list.innerHTML = '<div class="file-entry"><span class="name">Loading...</span></div>';

  try {
    const r = await fetch(`/api/files/list?path=${encodeURIComponent(dir)}`);
    const data = await r.json();
    renderFiles(data.files || [], data.current_path || '.');
  } catch (e) {
    list.innerHTML = '<div class="file-entry"><span class="name">Error loading files</span></div>';
  }
}

let currentFileDir = '.';

function renderFiles(files, path) {
  const list = document.getElementById('file-list');
  const pathEl = document.getElementById('current-path');
  currentFileDir = path;
  pathEl.textContent = `cross-compile/${path === '.' ? '' : path}`;

  list.innerHTML = '';

  // Parent directory link
  if (path !== '.') {
    const parent = document.createElement('div');
    parent.className = 'file-entry dir';
    parent.innerHTML = `<span class="icon">📁</span><span class="name">.. (parent)</span><span class="size"></span><span class="actions"></span>`;
    parent.addEventListener('click', () => {
      const parts = path.split('/');
      parts.pop();
      refreshFiles(parts.join('/') || '.');
    });
    list.appendChild(parent);
  }

  files.forEach(f => {
    const entry = document.createElement('div');
    entry.className = `file-entry${f.is_dir ? ' dir' : ''}`;

    const icon = f.is_dir ? '📁' : getFileIcon(f.name);
    const sizeStr = f.is_dir ? '' : formatSize(f.size);

    entry.innerHTML = `
      <span class="icon">${icon}</span>
      <span class="name">${f.name}</span>
      <span class="size">${sizeStr}</span>
      <span class="actions">
        ${f.is_dir ? '' : '<button class="dl-btn" title="Download">⬇</button>'}
        <button class="del-btn" title="Delete">🗑</button>
      </span>
    `;

    entry.addEventListener('click', (e) => {
      if (e.target.closest('.actions')) return;
      if (f.is_dir) {
        refreshFiles(f.path);
      } else {
        openFile(f.path);
      }
    });

    // Download
    const dlBtn = entry.querySelector('.dl-btn');
    if (dlBtn) {
      dlBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        window.open(`/api/files/download?path=${encodeURIComponent(f.path)}`);
      });
    }

    // Delete
    const delBtn = entry.querySelector('.del-btn');
    delBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm(`Delete "${f.name}"?`)) return;
      await fetch('/api/files/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ path: f.path }),
      });
      refreshFiles(currentFileDir);
    });

    list.appendChild(entry);
  });
}

function getFileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const icons = {
    py: '🐍', js: '🟨', ts: '🔷', cpp: '⚙', c: '⚙', h: '🔧',
    hpp: '🔧', cs: '☕', java: '☕', rs: '🦀', go: '🔵',
    sh: '💻', ps1: '🪟', bat: '🪟',
    html: '🌐', css: '🎨', json: '📋', xml: '📋',
    yaml: '📋', yml: '📋', md: '📝', txt: '📄',
    png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼', svg: '🖼',
    zip: '📦', tar: '📦', gz: '📦', exe: '⚡', dll: '🔗',
    pdf: '📕',
  };
  return icons[ext] || '📄';
}

function formatSize(bytes) {
  if (bytes === 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return `${size.toFixed(1)} ${units[i]}`;
}

// File upload
document.getElementById('file-upload-btn').addEventListener('click', () => {
  document.getElementById('file-input').click();
});

document.getElementById('file-input').addEventListener('change', async (e) => {
  const files = e.target.files;
  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', currentFileDir);
    await fetch('/api/files/upload', { method: 'POST', body: formData });
  }
  refreshFiles(currentFileDir);
  e.target.value = '';
});

document.getElementById('file-refresh').addEventListener('click', () => {
  refreshFiles(currentFileDir);
});

document.getElementById('file-new-folder').addEventListener('click', () => {
  const name = prompt('Folder name:');
  if (!name) return;
  // Create folder by uploading an empty placeholder
  const formData = new FormData();
  formData.append('file', new Blob([''], { type: 'text/plain' }), `.mkdir_${name}`);
  formData.append('path', currentFileDir);
  fetch('/api/files/upload', { method: 'POST', body: formData }).then(() => {
    refreshFiles(currentFileDir);
  });
});

// ─── AI Assistant ──────────────────────────────────────────────
const aiMessages = document.getElementById('ai-messages');
const aiInput = document.getElementById('ai-input');

async function sendAiMessage(message) {
  // Add user message
  const userDiv = document.createElement('div');
  userDiv.className = 'message user';
  userDiv.innerHTML = `<div class="msg-content">${escapeHtml(message)}</div>`;
  aiMessages.appendChild(userDiv);

  // Add AI thinking indicator
  const thinkDiv = document.createElement('div');
  thinkDiv.className = 'message ai';
  thinkDiv.id = 'ai-thinking';
  thinkDiv.innerHTML = '<div class="msg-content">Thinking...</div>';
  aiMessages.appendChild(thinkDiv);
  aiMessages.scrollTop = aiMessages.scrollHeight;

  // Use the port analysis API (we'll make it general-purpose)
  try {
    const r = await fetch('/api/ai/port', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: `// Question: ${message}\n// Analyze this for Windows→Linux porting guidance.`,
        source_lang: 'question',
        target_lang: 'linux',
      }),
    });
    const data = await r.json();

    document.getElementById('ai-thinking').remove();

    // Build a useful response
    let response = '';
    if (data.suggestions && data.suggestions.length > 0) {
      response = 'Here are general porting considerations:\n\n';
      data.suggestions.forEach(s => {
        response += `**${s.category}**\n`;
        s.items.forEach(i => { response += `- ${i}\n`; });
        response += '\n';
      });
    } else {
      response = 'For Windows→Linux porting, here are key areas to consider:\n\n'
        + '1. **API Translation**: Windows APIs (Win32, COM, DirectX) need Linux equivalents\n'
        + '2. **Build System**: Use CMake for cross-platform builds\n'
        + '3. **File Paths**: Use / instead of \\, or better, use a cross-platform path library\n'
        + '4. **Line Endings**: Linux uses LF, Windows uses CRLF\n'
        + '5. **Libraries**: Check for Linux equivalents of Windows-only libraries\n\n'
        + 'For specific help, paste your code in the Code Editor and click "Analyze Portability".';
    }

    const aiDiv = document.createElement('div');
    aiDiv.className = 'message ai';
    aiDiv.innerHTML = `<div class="msg-content">${response.replace(/\n/g, '<br>')}</div>`;
    aiMessages.appendChild(aiDiv);
  } catch (e) {
    document.getElementById('ai-thinking').remove();
    const errDiv = document.createElement('div');
    errDiv.className = 'message ai';
    errDiv.innerHTML = `<div class="msg-content">Error: ${e.message}</div>`;
    aiMessages.appendChild(errDiv);
  }

  aiMessages.scrollTop = aiMessages.scrollHeight;
}

document.getElementById('ai-send').addEventListener('click', () => {
  const msg = aiInput.value.trim();
  if (!msg) return;
  aiInput.value = '';
  sendAiMessage(msg);
});

aiInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('ai-send').click();
  }
});

document.getElementById('ai-analyze-current').addEventListener('click', () => {
  const code = editor.value;
  if (!code.trim()) {
    alert('No code in the editor. Write or open a file first.');
    return;
  }
  // Auto-analyze and switch to AI view
  const msg = `Please analyze this code for Windows→Linux portability:\n\n\`\`\`\n${code.substring(0, 500)}\n\`\`\`\n\nFull analysis in the Analysis panel on the right.`;
  // Trigger the analysis API
  fetch('/api/ai/port', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      code: code,
      source_lang: state.currentFile,
      target_lang: 'linux',
    }),
  }).then(r => r.json()).then(data => {
    showAnalysis(data);
  });
  sendAiMessage(msg);
  document.querySelector('.nav-btn[data-view="ai-assistant"]').click();
});

document.getElementById('ai-clear-chat').addEventListener('click', () => {
  aiMessages.innerHTML = `
    <div class="message ai">
      <div class="msg-content">
        Hello! I can help you analyze code for Windows→Linux porting.
        Open a file or paste code in the Code Editor, then click "Analyze Portability"
        or send me your code here.
      </div>
    </div>`;
});

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ─── Settings ───────────────────────────────────────────────────
function loadSettings() {
  document.getElementById('setting-username').value = state.settings.username;
  document.getElementById('setting-password').value = state.settings.password;
  document.getElementById('setting-host').value = state.settings.host;
  document.getElementById('setting-port').value = state.settings.port;
}

function saveSettings() {
  state.settings.username = document.getElementById('setting-username').value;
  state.settings.password = document.getElementById('setting-password').value;
  state.settings.host = document.getElementById('setting-host').value;
  state.settings.port = parseInt(document.getElementById('setting-port').value) || 5985;

  localStorage.setItem('winrm_username', state.settings.username);
  localStorage.setItem('winrm_password', state.settings.password);
  localStorage.setItem('winrm_host', state.settings.host);
  localStorage.setItem('winrm_port', state.settings.port);
}

document.getElementById('setting-username').addEventListener('change', saveSettings);
document.getElementById('setting-password').addEventListener('change', saveSettings);
document.getElementById('setting-host').addEventListener('change', saveSettings);
document.getElementById('setting-port').addEventListener('change', saveSettings);

document.getElementById('test-connection').addEventListener('click', async () => {
  saveSettings();
  const resultDiv = document.getElementById('connection-result');
  resultDiv.textContent = 'Testing...';

  const formData = new FormData();
  formData.append('username', state.settings.username);
  formData.append('password', state.settings.password);

  try {
    const r = await fetch('/api/winrm/check', {
      method: 'POST',
      body: formData,
    });
    const data = await r.json();
    if (data.success) {
      resultDiv.textContent = '✅ Connection successful!';
      resultDiv.style.color = 'var(--green)';
    } else {
      resultDiv.textContent = '❌ ' + (data.error || 'Connection failed');
      resultDiv.style.color = 'var(--red)';
    }
  } catch (e) {
    resultDiv.textContent = '❌ Error: ' + e.message;
    resultDiv.style.color = 'var(--red)';
  }
});

document.getElementById('view-winrm-guide').addEventListener('click', async () => {
  const r = await fetch('/api/winrm/setup-guide');
  const data = await r.json();
  document.getElementById('winrm-guide-text').textContent = data.guide;
  document.getElementById('winrm-guide-modal').style.display = 'flex';
});

document.querySelector('.modal-close')?.addEventListener('click', () => {
  document.getElementById('winrm-guide-modal').style.display = 'none';
});

window.addEventListener('click', (e) => {
  const modal = document.getElementById('winrm-guide-modal');
  if (e.target === modal) {
    modal.style.display = 'none';
  }
});

// ─── Terminal Toggle ────────────────────────────────────────────
document.getElementById('terminal-winrm-toggle').addEventListener('click', () => {
  if (state.terminalMode === 'linux') {
    state.terminalMode = 'winrm';
    terminalMode.className = 'tag tag-windows';
    terminalMode.textContent = '🪟 Windows VM';
    terminalPrompt.textContent = 'PS> ';
    terminalOutput.textContent += '\n[Switched to Windows VM — WinRM terminal]\n';
  } else {
    state.terminalMode = 'linux';
    terminalMode.className = 'tag tag-linux';
    terminalMode.textContent = '🐧 Linux Host';
    terminalPrompt.textContent = `${getUser()}@host:~$ `;
    terminalOutput.textContent += '\n[Switched to Linux host terminal]\n';
  }
});

// ─── Polling for VM status ──────────────────────────────────────
setInterval(refreshDashboard, 15000);

// ─── Init ───────────────────────────────────────────────────────
loadSettings();
connectTerminal();
refreshFileTree();

console.log('Windows Port Console initialized.');
