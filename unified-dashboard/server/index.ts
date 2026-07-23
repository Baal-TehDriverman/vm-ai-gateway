import fs from 'fs';
import path from 'path';
import express from "express";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = 3000;

app.use(express.json());

// Helper to safely get Gemini client
function getGeminiClient() {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return null;
  }
  return new GoogleGenAI({
    apiKey,
    httpOptions: {
      headers: {
        "User-Agent": "lilith-unified-dashboard",
      },
    },
  });
}

// GitHub API proxy helper
function getGithubHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "User-Agent": "Lilith-Unified-Dashboard/1.0",
    Accept: "application/vnd.github.v3+json",
  };

  const token = process.env.GITHUB_TOKEN || "";

  if (token) {
    headers["Authorization"] = token.startsWith("Bearer ") || token.startsWith("token ")
      ? token
      : `token ${token}`;
  }

  return headers;
}

function normalizeUsername(username: string): string {
  const clean = (username || "").trim();
  const lower = clean.toLowerCase();
  if (
    lower === "thedriverman" ||
    lower === "the-driverman" ||
    lower === "the driver man" ||
    lower === "driverman" ||
    lower === "driver-man-coop"
  ) {
    return "The-Driver-Man";
  }
  if (lower === "lilithsystems" || lower === "lilith-systems") {
    return "Lilith-Systems";
  }
  if (lower === "baaltehdriverman" || lower === "baal-tehdriverman") {
    return "Baal-TehDriverman";
  }
  return clean;
}

// ===== GITHUB API ROUTES =====

// 1. Get User Profile
app.get("/api/github/user/:username", async (req, res) => {
  try {
    const rawUsername = req.params.username;
    const username = normalizeUsername(rawUsername);
    let response = await fetch(`https://api.github.com/users/${encodeURIComponent(username)}`, {
      headers: getGithubHeaders(),
    });
    if (!response.ok) {
      response = await fetch(`https://api.github.com/orgs/${encodeURIComponent(username)}`, {
        headers: getGithubHeaders(),
      });
    }
    if (!response.ok) {
      return res.status(response.status).json({ error: `GitHub API error: ${response.statusText}` });
    }
    const data = await response.json();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ error: error.message || "Failed to fetch user profile" });
  }
});

// 2. Get User Repositories
app.get("/api/github/user/:username/repos", async (req, res) => {
  try {
    const rawUsername = req.params.username;
    const username = normalizeUsername(rawUsername);
    const headers = getGithubHeaders();

    let repos: any[] = [];

    // Strategy A: /users/:username/repos
    const userRes = await fetch(
      `https://api.github.com/users/${encodeURIComponent(username)}/repos?per_page=100&sort=updated`,
      { headers }
    );
    if (userRes.ok) {
      const data = await userRes.json();
      if (Array.isArray(data) && data.length > 0) {
        repos = data;
      }
    }

    // Strategy B: /orgs/:username/repos
    if (repos.length === 0) {
      const orgRes = await fetch(
        `https://api.github.com/orgs/${encodeURIComponent(username)}/repos?per_page=100&sort=updated`,
        { headers }
      );
      if (orgRes.ok) {
        const data = await orgRes.json();
        if (Array.isArray(data) && data.length > 0) {
          repos = data;
        }
      }
    }

    // Strategy C: Authenticated user repos filter
    if (repos.length === 0) {
      const authRes = await fetch(`https://api.github.com/user/repos?per_page=100&type=all`, { headers });
      if (authRes.ok) {
        const allData = await authRes.json();
        if (Array.isArray(allData)) {
          repos = allData.filter(
            (r: any) => r.owner?.login?.toLowerCase() === username.toLowerCase()
          );
        }
      }
    }

    res.json(repos);
  } catch (error: any) {
    res.status(500).json({ error: error.message || "Failed to fetch repositories" });
  }
});

// 3. Get Repository README
app.get("/api/github/repo/:owner/:repo/readme", async (req, res) => {
  try {
    const { owner, repo } = req.params;
    const response = await fetch(`https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/readme`, {
      headers: {
        ...getGithubHeaders(),
        Accept: "application/vnd.github.v3.raw",
      },
    });
    if (!response.ok) {
      return res.status(response.status).send("No README found or error fetching README.");
    }
    const text = await response.text();
    res.send(text);
  } catch (error: any) {
    res.status(500).send("Error fetching README.");
  }
});

// 4. Get Repository File Tree / Contents
app.get("/api/github/repo/:owner/:repo/contents*", async (req, res) => {
  try {
    const { owner, repo } = req.params;
    const pathParam = req.params[0] || "";
    const cleanPath = pathParam.startsWith("/") ? pathParam.slice(1) : pathParam;
    const url = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/${encodeURIComponent(cleanPath)}`;
    const response = await fetch(url, { headers: getGithubHeaders() });

    if (!response.ok) {
      return res.status(response.status).json({ error: "Failed to fetch repository contents" });
    }
    const data = await response.json();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ error: error.message || "Failed to fetch contents" });
  }
});

// 5. Get Repo Commits
app.get("/api/github/repo/:owner/:repo/commits", async (req, res) => {
  try {
    const { owner, repo } = req.params;
    const response = await fetch(`https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/commits?per_page=15`, {
      headers: getGithubHeaders(),
    });
    if (!response.ok) {
      return res.status(response.status).json([]);
    }
    const data = await response.json();
    res.json(data);
  } catch (error: any) {
    res.json([]);
  }
});

// 6. Get Repo Language Breakdown
app.get("/api/github/repo/:owner/:repo/languages", async (req, res) => {
  try {
    const { owner, repo } = req.params;
    const response = await fetch(`https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/languages`, {
      headers: getGithubHeaders(),
    });
    if (!response.ok) {
      return res.status(response.status).json({});
    }
    const data = await response.json();
    res.json(data);
  } catch (error: any) {
    res.json({});
  }
});

// ===== GEMINI AI ROUTES =====

// 7. Gemini AI - Analyze Developer Profile & Archetype
app.post("/api/gemini/analyze-profile", async (req, res) => {
  try {
    const { username, profile, repos } = req.body;
    const ai = getGeminiClient();

    if (!ai) {
      return res.status(500).json({ error: "GEMINI_API_KEY environment variable is not configured." });
    }

    const reposSummary = repos
      ?.map(
        (r: any) =>
          `- ${r.name} (${r.language || "Unknown language"}): ${r.description || "No description"} | Stars: ${r.stargazers_count} | Size: ${r.size}KB | Updated: ${r.updated_at}`
      )
      .join("\n");

    const prompt = `
Analyze the following GitHub developer portfolio and synthesize a high-level Developer Intelligence Briefing.

Developer Username: ${username}
Public Repos Count: ${profile?.public_repos || repos?.length || 0}
Account Created: ${profile?.created_at || "Unknown"}
Repositories:
${reposSummary || "No repos listed"}

Provide a detailed JSON response matching this schema:
{
  "archetype": "e.g. Sovereign Systems & AI Game Engine Architect",
  "summary": "3-4 sentence comprehensive overview of the developer's focus, technical ambition, and domain expertise.",
  "primaryDomains": ["Domain 1", "Domain 2", "Domain 3"],
  "signatureInnovations": ["Key Innovation 1", "Key Innovation 2", "Key Innovation 3"],
  "technicalStrengths": ["Strength 1", "Strength 2", "Strength 3", "Strength 4"],
  "suggestedCollaborations": "Suggestions for potential open source collaborations or next project directions."
}
Return valid JSON without markdown code fences.
`;

    const response = await ai.models.generateContent({
      model: "gemini-3.6-flash",
      contents: prompt,
      config: {
        responseMimeType: "application/json",
      },
    });

    const resultText = response.text || "{}";
    const data = JSON.parse(resultText);
    res.json(data);
  } catch (error: any) {
    console.error("Gemini analyze-profile error:", error);
    res.status(500).json({ error: error.message || "Failed to analyze developer profile" });
  }
});

// 8. Gemini AI - Analyze Specific Repository
app.post("/api/gemini/analyze-repo", async (req, res) => {
  try {
    const { repo, readmeText, languageBreakdown } = req.body;
    const ai = getGeminiClient();
    if (!ai) {
      return res.status(500).json({ error: "GEMINI_API_KEY environment variable is not configured." });
    }

    const prompt = `
Analyze this specific GitHub Repository in depth:

Repository Name: ${repo.name}
Full Name: ${repo.full_name}
Description: ${repo.description || "None"}
Primary Language: ${repo.language || "Unknown"}
Languages Breakdown: ${JSON.stringify(languageBreakdown || {})}
Size: ${repo.size} KB
Stars: ${repo.stargazers_count} | Forks: ${repo.forks_count}
README Excerpt:
${readmeText ? readmeText.slice(0, 3000) : "No README available"}

Generate an Architecture & Intelligence Evaluation JSON object:
{
  "architectureOverview": "Comprehensive paragraph explaining what this project does and how it is structured.",
  "coreComponents": ["Component 1", "Component 2", "Component 3"],
  "techStackHighlights": ["Highlight 1", "Highlight 2", "Highlight 3"],
  "useCases": ["Use Case 1", "Use Case 2"],
  "potentialEnhancements": ["Enhancement 1", "Enhancement 2", "Enhancement 3"],
  "complexityScore": 8.5
}
Return valid JSON without markdown code fences.
`;

    const response = await ai.models.generateContent({
      model: "gemini-3.6-flash",
      contents: prompt,
      config: {
        responseMimeType: "application/json",
      },
    });

    const data = JSON.parse(response.text || "{}");
    res.json(data);
  } catch (error: any) {
    console.error("Gemini analyze-repo error:", error);
    res.status(500).json({ error: error.message || "Failed to analyze repository" });
  }
});

// 9. Gemini AI - Interactive Q&A Chat
app.post("/api/gemini/chat", async (req, res) => {
  try {
    const { username, selectedRepo, userQuery, history } = req.body;
    const ai = getGeminiClient();
    if (!ai) {
      return res.status(500).json({ error: "GEMINI_API_KEY is not configured." });
    }

    const systemInstruction = `You are a world-class senior staff engineer and AI code analyst specializing in developer portfolio evaluation and repository architecture.
You are helping the user explore developer ${username}${selectedRepo ? `'s repository ${selectedRepo.name}` : ""}.
Provide clear, authoritative, technically deep, and concise answers.`;

    const prompt = `
Context: Developer = ${username}, Selected Repo = ${selectedRepo ? selectedRepo.name + " (" + (selectedRepo.description || "No description") + ")" : "All repos"}

User Question: ${userQuery}
`;

    const response = await ai.models.generateContent({
      model: "gemini-3.6-flash",
      contents: prompt,
      config: {
        systemInstruction,
      },
    });

    res.json({ text: response.text });
  } catch (error: any) {
    console.error("Gemini chat error:", error);
    res.status(500).json({ error: error.message || "Gemini query failed" });
  }
});

// ===== LILITH GATEWAY PROXY ROUTES =====

const GATEWAY_BASE = "http://localhost:8080";

// Proxy middleware for Lilith Gateway
async function proxyToGateway(req: express.Request, res: express.Response, gatewayPath: string) {
  try {
    const url = `${GATEWAY_BASE}${gatewayPath}${req.url.replace('/api/gateway', '')}`;
    const response = await fetch(url, {
      method: req.method,
      headers: {
        'Content-Type': 'application/json',
        ...(req.headers.authorization && { 'Authorization': req.headers.authorization }),
      },
      body: req.method !== 'GET' && req.method !== 'HEAD' ? JSON.stringify(req.body) : undefined,
    });

    const data = await response.json().catch(() => response.text());
    res.status(response.status).json(data);
  } catch (error: any) {
    console.error(`Gateway proxy error for ${gatewayPath}:`, error);
    res.status(502).json({ error: `Gateway proxy error: ${error.message}` });
  }
}

// Apps
app.get("/api/gateway/apps", (req, res) => proxyToGateway(req, res, "/api/apps"));
app.get("/api/gateway/apps/search/:query", (req, res) => proxyToGateway(req, res, "/api/apps/search/" + req.params.query));
app.post("/api/gateway/apps/launch/:appName", (req, res) => proxyToGateway(req, res, "/api/apps/launch/" + req.params.appName));

// VMs
app.get("/api/gateway/vms", (req, res) => proxyToGateway(req, res, "/api/vms"));
app.post("/api/gateway/vms/:action/:vmName", (req, res) => proxyToGateway(req, res, `/api/vms/${req.params.action}/${req.params.vmName}`));
app.post("/api/gateway/vms/console/:vmName", (req, res) => proxyToGateway(req, res, "/api/vms/console/" + req.params.vmName));
app.post("/api/gateway/vms/manager", (req, res) => proxyToGateway(req, res, "/api/vms/manager"));

// System Status
app.get("/api/gateway/status", (req, res) => proxyToGateway(req, res, "/api/status"));

// Engine
app.get("/api/gateway/engine/status", (req, res) => proxyToGateway(req, res, "/api/engine/status"));
app.post("/api/gateway/engine/build", (req, res) => proxyToGateway(req, res, "/api/engine/build"));
app.post("/api/gateway/engine/test", (req, res) => proxyToGateway(req, res, "/api/engine/test"));
app.get("/api/gateway/engine/artifacts", (req, res) => proxyToGateway(req, res, "/api/engine/artifacts"));
app.get("/api/gateway/engine/rom/status", (req, res) => proxyToGateway(req, res, "/api/engine/rom/status"));

// MSN Cyberpunk
app.get("/api/gateway/msn/status", (req, res) => proxyToGateway(req, res, "/api/msn/status"));
app.get("/api/gateway/msn/cyberpunk", (req, res) => proxyToGateway(req, res, "/api/msn/cyberpunk"));
app.post("/api/gateway/verify-mod-deployment", (req, res) => proxyToGateway(req, res, "/api/verify-mod-deployment"));

// Abyssal
app.get("/api/gateway/abyssal/status", (req, res) => proxyToGateway(req, res, "/api/abyssal/status"));

// Categories
app.get("/api/gateway/categories", (req, res) => proxyToGateway(req, res, "/api/categories"));

// LLM Proxy
app.post("/v1/chat/completions", async (req, res) => {
  try {
    const response = await fetch(`${GATEWAY_BASE}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(req.headers['x-api-key'] && { 'x-api-key': req.headers['x-api-key'] as string }),
      },
      body: JSON.stringify(req.body),
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error: any) {
    res.status(502).json({ error: `LLM proxy error: ${error.message}` });
  }
});

app.get("/v1/models", async (req, res) => {
  try {
    const response = await fetch(`${GATEWAY_BASE}/v1/models`);
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error: any) {
    res.status(502).json({ error: `LLM proxy error: ${error.message}` });
  }
});

// ===== KAIROS DREAM ROUTES =====

// In-memory dream storage (replace with SQLite in production)
const dreamStore: any[] = [];

app.post("/api/dream/trigger", async (req, res) => {
  try {
    const { session = 'zelda-engine' } = req.body;
    
    // Trigger dream cycle via Kairos scheduler
    const { exec } = await import('child_process');
    const { promisify } = await import('util');
    const execAsync = promisify(exec);
    
    // Run the dream scheduler once
    await execAsync(`python3 /home/tehlappy/Projects/Dev Console/kairos_clean.py --session ${session} --once`, {
      cwd: '/home/tehlappy/Projects/Dev Console',
      timeout: 60000,
    });
    
    res.json({ status: 'triggered', session });
  } catch (error: any) {
    console.error('Dream trigger error:', error);
    res.status(500).json({ error: error.message });
  }
});

app.get("/api/dream/history/:session", (req, res) => {
  const session = req.params.session;
  const filtered = dreamStore.filter(d => d.session === session);
  res.json({ dreams: filtered, count: filtered.length });
});

app.get("/api/dreams", (req, res) => {
  const limit = parseInt(req.query.limit as string) || 50;
  const session = req.query.session as string;
  
  let filtered = dreamStore;
  if (session) {
    filtered = filtered.filter(d => d.session === session);
  }
  
  res.json({ dreams: filtered.slice(-limit), count: filtered.length });
});

// ===== OBSIDIAN VAULT ROUTES =====

const OBSIDIAN_VAULT = "/home/tehlappy/Documents/Obsidian Vault";

app.get("/api/vault/index", (req, res) => {
  try {
    const fs = require('fs');
    const path = require('path');
    
    function scanDir(dir: string): any[] {
      const items: any[] = [];
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      
      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (!entry.name.startsWith('.')) {
            items.push({
              name: entry.name,
              type: 'folder',
              path: fullPath,
              children: scanDir(fullPath),
            });
          }
        } else if (entry.name.endsWith('.md')) {
          const stats = fs.statSync(fullPath);
          items.push({
            name: entry.name.replace('.md', ''),
            type: 'file',
            path: fullPath,
            size: stats.size,
            modified: stats.mtime,
          });
        }
      }
      return items;
    }
    
    const vaultIndex = scanDir(OBSIDIAN_VAULT);
    res.json({ vault: vaultIndex });
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.get("/api/vault/file/*", (req, res) => {
  try {
    const fs = require('fs');
    const filePath = req.params[0];
    const fullPath = path.join(OBSIDIAN_VAULT, filePath + (filePath.endsWith('.md') ? '' : '.md'));
    
    if (fs.existsSync(fullPath)) {
      const content = fs.readFileSync(fullPath, 'utf-8');
      res.json({ content, path: fullPath });
    } else {
      res.status(404).json({ error: 'File not found' });
    }
  } catch (error: any) {
    res.status(500).json({ error: error.message });
  }
});

app.get("/api/vault/search", (req, res) => {
  try {
    const query = req.query.q as string;
    const { execSync } = require('child_process');
    
    if (!query) {
      return res.json({ results: [] });
    }
    
    // Use rg for fast search
    const result = execSync(`cd "${OBSIDIAN_VAULT}" && rg -i -l "${query.replace(/"/g, '\\"')}" --type md 2>/dev/null | head -20`, {
      encoding: 'utf-8',
      timeout: 10000,
    });
    
    const files = result.trim().split('\n').filter(Boolean);
    const results = files.map(file => {
      const fullPath = path.join(OBSIDIAN_VAULT, file);
      const fs = require('fs');
      const content = fs.readFileSync(fullPath, 'utf-8');
      const lines = content.split('\n');
      const matchLine = lines.find(l => l.toLowerCase().includes(query.toLowerCase()));
      return {
        file,
        path: fullPath,
        preview: matchLine ? matchLine.trim().slice(0, 200) : '',
      };
    });
    
    res.json({ results, count: results.length });
  } catch (error: any) {
    res.json({ results: [], count: 0 });
  }
});

// ===== KNOWLEDGE GRAPH API =====

const KNOWLEDGE_GRAPH_PATH = path.join(process.cwd(), "public", "msn-knowledge-graph.json");

app.get("/api/knowledge-graph/msn", (req, res) => {
  try {
    const resolvedPath = path.resolve(KNOWLEDGE_GRAPH_PATH);
    console.log(`[KG] Loading knowledge graph from: ${resolvedPath}`);
    if (fs.existsSync(resolvedPath)) {
      const raw = fs.readFileSync(resolvedPath, 'utf-8');
      const data = JSON.parse(raw);
      res.json(data);
    } else {
      res.json({ title: "No knowledge graph available", nodes: [], edges: [], path: resolvedPath });
    }
  } catch (error: any) {
    res.json({ title: "Error loading knowledge graph", nodes: [], edges: [], error: error.message });
  }
});

// ===== HEALTH CHECK =====
app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "lilith-unified-dashboard", version: "2.0.0" });
});

// ===== VITE & STATIC FILE SETUP =====
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`🜏 Lilith Unified Dashboard — http://0.0.0.0:${PORT}`);
    console.log(`  Frontend: http://localhost:${PORT}`);
    console.log(`  API:      http://localhost:${PORT}/api/*`);
    console.log(`  Gateway:  http://localhost:8080`);
  });
}

startServer();