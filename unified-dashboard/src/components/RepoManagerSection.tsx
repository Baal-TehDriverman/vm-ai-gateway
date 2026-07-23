import React, { useState } from 'react';
import { GitBranch, RefreshCw, ExternalLink, ChevronDown, ChevronRight, CheckCircle, AlertCircle, Loader2, Terminal } from 'lucide-react';

interface RepoInfo {
  name: string;
  status: string;
  branch: string;
  dirty_files: number;
  org: string;
}

const ORGS = [
  { id: 'Baal-TehDriverman', label: 'Baal-TehDriverman', color: 'purple' },
  { id: 'Lilith-Systems', label: 'Lilith-Systems', color: 'cyan' },
  { id: 'The-Driver-Man', label: 'The-Driver-Man', color: 'emerald' },
];

const DEMO_REPOS: RepoInfo[] = [
  { name: 'vm-ai-gateway', status: 'clean', branch: 'master', dirty_files: 0, org: 'Baal-TehDriverman' },
  { name: 'devdashboard-public', status: 'clean', branch: 'main', dirty_files: 0, org: 'Baal-TehDriverman' },
  { name: 'msn-integration', status: 'dirty', branch: 'master', dirty_files: 1, org: 'Lilith-Systems' },
  { name: 'lilith-frankenstein', status: 'clean', branch: 'main', dirty_files: 0, org: 'Lilith-Systems' },
  { name: 'Sovereign-Core', status: 'clean', branch: 'master', dirty_files: 0, org: 'Lilith-Systems' },
  { name: 'babe-unified-field', status: 'clean', branch: 'main', dirty_files: 0, org: 'Lilith-Systems' },
  { name: 'dm-dispatch-dashboard', status: 'clean', branch: 'main', dirty_files: 0, org: 'The-Driver-Man' },
  { name: 'dm-driver-portal', status: 'clean', branch: 'main', dirty_files: 0, org: 'The-Driver-Man' },
];

export const RepoManagerSection: React.FC = () => {
  const [repos] = useState<RepoInfo[]>(DEMO_REPOS);
  const [expandedOrg, setExpandedOrg] = useState<string | null>('Baal-TehDriverman');
  const [isPushing, setIsPushing] = useState(false);
  const [pushLog, setPushLog] = useState<string[]>([]);
  const [showLog, setShowLog] = useState(false);

  const getApplicableOrgs = (): string[] => {
    const orgs = new Set(repos.map(r => r.org));
    return ORGS.filter(o => orgs.has(o.id)).map(o => o.id);
  };

  const handlePushAll = async () => {
    setIsPushing(true);
    setShowLog(true);
    setPushLog(['[START] Pushing all repositories...']);
    
    const applicable = getApplicableOrgs();
    for (const orgId of applicable) {
      const orgRepos = repos.filter(r => r.org === orgId);
      for (const repo of orgRepos) {
        setPushLog(prev => [...prev, `[PUSH] ${orgId}/${repo.name}...`]);
        await new Promise(r => setTimeout(r, 500));
        setPushLog(prev => [...prev, `  ✓ ${repo.name} pushed successfully`]);
      }
    }
    setPushLog(prev => [...prev, '[DONE] All repositories pushed']);
    setIsPushing(false);
  };

  const orgRepos = (orgId: string) => repos.filter(r => r.org === orgId);

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="glass rounded-2xl p-6 border border-slate-800/60">
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-xl bg-emerald-950/50 border border-emerald-800/60">
            <GitBranch className="w-6 h-6 text-emerald-400" />
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-bold text-white">Repository Manager</h2>
            <p className="text-slate-400">Push all repos • Track dirty files • Monitor status across 3 orgs</p>
          </div>
          <div className="flex gap-2">
            <button onClick={handlePushAll} disabled={isPushing} className="btn-primary">
              {isPushing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Push All
            </button>
          </div>
        </div>
      </div>

      {/* Organization Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {ORGS.map(org => (
          <button
            key={org.id}
            onClick={() => setExpandedOrg(expandedOrg === org.id ? null : org.id)}
            className={`glass rounded-xl p-5 border transition-all ${
              expandedOrg === org.id
                ? `border-${org.color}-500/60 bg-slate-900/80`
                : 'border-slate-800/60 hover:border-slate-700'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className={`px-3 py-1 rounded-full text-xs font-bold bg-${org.color}-950 text-${org.color}-400 border border-${org.color}-800`}>
                {org.id}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-400">{orgRepos(org.id).length} repos</span>
                {expandedOrg === org.id ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
              </div>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle className="w-3.5 h-3.5" />
                {orgRepos(org.id).filter(r => r.status === 'clean').length} clean
              </span>
              <span className="flex items-center gap-1 text-amber-400">
                <AlertCircle className="w-3.5 h-3.5" />
                {orgRepos(org.id).filter(r => r.status !== 'clean').length} dirty
              </span>
            </div>
          </button>
        ))}
      </div>

      {/* Expanded Org Repos */}
      {expandedOrg && (
        <div className="glass rounded-2xl border border-slate-800/60 overflow-hidden">
          <div className="p-4 border-b border-slate-800/60 bg-slate-900/50">
            <h3 className="font-bold text-white text-lg">{expandedOrg} — Repositories</h3>
          </div>
          <div className="divide-y divide-slate-800/60">
            {orgRepos(expandedOrg).map(repo => (
              <div key={repo.name} className="flex items-center justify-between p-4 hover:bg-slate-900/30 transition-colors">
                <div className="flex items-center gap-3">
                  <GitBranch className={`w-4 h-4 ${repo.status === 'clean' ? 'text-emerald-400' : 'text-amber-400'}`} />
                  <div>
                    <p className="font-medium text-white">{repo.name}</p>
                    <p className="text-xs text-slate-400">{repo.branch} branch</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {repo.dirty_files > 0 ? (
                    <span className="text-xs text-amber-400 bg-amber-950/50 px-2 py-1 rounded border border-amber-800/60">
                      {repo.dirty_files} dirty
                    </span>
                  ) : (
                    <span className="text-xs text-emerald-400 bg-emerald-950/50 px-2 py-1 rounded border border-emerald-800/60">
                      clean
                    </span>
                  )}
                  <a href={`https://github.com/${repo.org}/${repo.name}`} target="_blank" rel="noopener noreferrer"
                    className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-all">
                    <ExternalLink className="w-4 h-4" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Push Log */}
      {showLog && (
        <div className="glass rounded-2xl p-4 border border-slate-800/60">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <h3 className="font-bold text-white text-sm">Push Log</h3>
            </div>
            <button onClick={() => setShowLog(false)} className="text-xs text-slate-400 hover:text-white">
              Close
            </button>
          </div>
          <div className="bg-slate-950 rounded-lg p-3 max-h-60 overflow-y-auto font-mono text-xs space-y-1">
            {pushLog.map((line, i) => (
              <p key={i} className={line.startsWith('[DONE]') ? 'text-emerald-400' : line.startsWith('[PUSH]') ? 'text-cyan-300' : 'text-slate-400'}>
                {line}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};