const API_BASE = '/api';
const GATEWAY_BASE = 'http://localhost:8080/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `HTTP ${response.status}`);
  }
  
  return response.json();
}

// GitHub API
export async function fetchGitHubUser(username: string) {
  return fetchJson(`${API_BASE}/github/user/${encodeURIComponent(username)}`);
}

export async function fetchGitHubRepos(username: string) {
  return fetchJson(`${API_BASE}/github/user/${encodeURIComponent(username)}/repos`);
}

export async function fetchRepoReadme(owner: string, repo: string) {
  const response = await fetch(`${API_BASE}/github/repo/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/readme`);
  if (!response.ok) throw new Error('README not found');
  return response.text();
}

export async function fetchRepoContents(owner: string, repo: string, path: string = '') {
  return fetchJson(`${API_BASE}/github/repo/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/${encodeURIComponent(path)}`);
}

export async function fetchRepoCommits(owner: string, repo: string) {
  return fetchJson(`${API_BASE}/github/repo/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/commits`);
}

export async function fetchRepoLanguages(owner: string, repo: string) {
  return fetchJson(`${API_BASE}/github/repo/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/languages`);
}

// AI API
export async function analyzeProfile(username: string, profile: any, repos: any[]) {
  return fetchJson(`${API_BASE}/gemini/analyze-profile`, {
    method: 'POST',
    body: JSON.stringify({ username, profile, repos }),
  });
}

export async function analyzeRepo(repo: any, readmeText: string, languageBreakdown: any) {
  return fetchJson(`${API_BASE}/gemini/analyze-repo`, {
    method: 'POST',
    body: JSON.stringify({ repo, readmeText, languageBreakdown }),
  });
}

export async function chatWithAi(username: string, selectedRepo: any | null, userQuery: string, history: any[]) {
  return fetchJson(`${API_BASE}/gemini/chat`, {
    method: 'POST',
    body: JSON.stringify({ username, selectedRepo, userQuery, history }),
  });
}

// Lilith Gateway API
export async function fetchSystemStatus() {
  return fetchJson(`${GATEWAY_BASE}/status`);
}

export async function fetchApps() {
  return fetchJson(`${GATEWAY_BASE}/apps`);
}

export async function fetchVms() {
  return fetchJson(`${GATEWAY_BASE}/vms`);
}

export async function launchApp(appName: string, token: string) {
  return fetchJson(`${GATEWAY_BASE}/apps/launch/${encodeURIComponent(appName)}`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
  });
}

export async function vmAction(action: string, vmName: string, token: string) {
  return fetchJson(`${GATEWAY_BASE}/vms/${action}/${encodeURIComponent(vmName)}`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
  });
}

export async function fetchEngineStatus() {
  return fetchJson(`${GATEWAY_BASE}/engine/status`);
}

export async function triggerEngineBuild(buildType: string = 'Debug', clean: boolean = false, target: string = '', token: string) {
  return fetchJson(`${GATEWAY_BASE}/engine/build`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({ build_type: buildType, clean, target }),
  });
}

export async function runEngineTests(token: string) {
  return fetchJson(`${GATEWAY_BASE}/engine/test`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
  });
}

export async function fetchEngineArtifacts() {
  return fetchJson(`${GATEWAY_BASE}/engine/artifacts`);
}

export async function fetchRomStatus() {
  return fetchJson(`${GATEWAY_BASE}/engine/rom/status`);
}

export async function fetchMsnStatus() {
  return fetchJson(`${GATEWAY_BASE}/msn/status`);
}

export async function fetchMsnCyberpunkStatus() {
  return fetchJson(`${GATEWAY_BASE}/msn/cyberpunk`);
}

export async function fetchAbyssalStatus() {
  return fetchJson(`${GATEWAY_BASE}/abyssal/status`);
}

export async function verifyModDeployment(token: string) {
  return fetchJson(`${GATEWAY_BASE}/verify-mod-deployment`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
  });
}

// Kairos Dream API
export async function triggerDreamCycle(session: string, token: string) {
  return fetchJson(`${GATEWAY_BASE}/dream/trigger`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({ session }),
  });
}

export async function fetchDreamHistory(session: string) {
  return fetchJson(`${GATEWAY_BASE}/dream/history/${encodeURIComponent(session)}`);
}

// WebSocket connection for real-time updates
export function createWebSocket(url: string): WebSocket {
  return new WebSocket(url);
}