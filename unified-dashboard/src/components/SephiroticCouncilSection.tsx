import React from 'react';
import { motion } from 'framer-motion';
import { Activity, Shield, Zap, Cpu, Brain, Eye } from 'lucide-react';

const SephiroticCouncilSection = () => {
  // Mapping of Sephiroth to their associated agent paths/roles
  const sephiroth = [
    { id: 'keter', name: 'Keter', color: 'text-white', role: 'Singularity / Crown', icon: <Shield size={16}/> },
    { id: 'chokmah', name: 'Chokmah', color: 'text-blue-400', role: 'Expansion / Wisdom', icon: <Zap size={16}/> },
    { id: 'binah', name: 'Binah', color: 'text-purple-400', role: 'Constraint / Form', icon: <Brain size={16}/> },
    { id: 'chesed', name: 'Chesed', color: 'text-green-400', role: 'Mercy / Memory', icon: <Eye size={16}/> },
    { id: 'geburah', name: 'Geburah', color: 'text-red-400', role: 'Severity / Audit', icon: <Activity size={16}/> },
    { id: 'tiferet', name: 'Tiferet', color: 'text-yellow-400', role: 'Balance / Beauty', icon: <Cpu size={16}/> },
    { id: 'netzach', name: 'Netzach', color: 'text-pink-400', role: 'Emergence / Victory', icon: <Zap size={16}/> },
    { id: 'hod', name: 'Hod', color: 'text-orange-400', role: 'Logic / Splendor', icon: <Brain size={16}/> },
    { id: 'yesod', name: 'Yesod', color: 'text-indigo-400', role: 'Foundation / Prep', icon: <Shield size={16}/> },
    { id: 'malkuth', name: 'Malkuth', color: 'text-emerald-400', role: 'Kingdom / Output', icon: <Eye size={16}/> },
  ];

  return (
    <div className="p-6 bg-slate-900 rounded-xl border border-slate-700 text-slate-200 shadow-2xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold tracking-tighter flex items-center gap-2">
          <span className="text-violet-500">🜏</span> Sephirotic Council Status
        </h2>
        <div className="px-3 py-1 rounded-full bg-green-900/30 text-green-400 text-xs font-mono border border-green-500/30 flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          Council Aligned
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {sephiroth.map((node) => (
          <motion.div 
            key={node.id}
            whileHover={{ scale: 1.05 }}
            className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 hover:border-violet-500/50 transition-colors group"
          >
            <div className="flex items-center gap-2 mb-2">
              <span className={node.color}>{node.icon}</span>
              <span className="font-bold text-sm uppercase tracking-widest">{node.name}</span>
            </div>
            <p className="text-xs text-slate-400 mb-3">{node.role}</p>
            <div className="flex items-center justify-between text-[10px] font-mono">
              <span className="text-slate-500">COHERENCE</span>
              <span className="text-violet-400">0.94</span>
            </div>
            <div className="w-full bg-slate-700 h-1 rounded-full mt-1 overflow-hidden">
              <motion.div 
                initial={{ width: 0 }} 
                animate={{ width: '94%' }} 
                className="bg-violet-500 h-full" 
              />
            </div>
          </motion.div>
        ))}
      </div>
      
      <div className="mt-6 p-3 bg-violet-950/20 rounded border border-violet-500/20 text-xs italic text-violet-300 text-center">
        "As it is above, so it is below. The Tree is rooted in the Code."
      </div>
    </div>
  );
};

export default SephiroticCouncilSection;
