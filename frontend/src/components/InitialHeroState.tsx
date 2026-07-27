import { useState } from 'react';

export interface HeroProps {
  onAnalyze: (repoUrl: string) => void;
}

const SAMPLE_REPOS = [
  { label: 'laravel/framework', url: 'https://github.com/laravel/framework' },
  { label: 'fastapi/fastapi', url: 'https://github.com/fastapi/fastapi' },
  { label: 'henrichile/AsistenciaSTM', url: 'https://github.com/henrichile/AsistenciaSTM', highlight: true },
];

function InitialHeroState({ onAnalyze }: HeroProps) {
  const [repoUrl, setRepoUrl] = useState('');
  const isValid = /^https?:\/\/.+/.test(repoUrl.trim());

  const handleSubmit = () => {
    if (isValid) onAnalyze(repoUrl.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && isValid) handleSubmit();
  };

  return (
    <div className="bg-[#0B0F17] text-white min-h-screen font-sans flex flex-col">
      {/* HEADER */}
      <header className="h-12 border-b border-slate-800/80 px-8 flex items-center justify-end bg-[#0B0F17]/90 backdrop-blur-md sticky top-0 z-50">
        <div className="text-xs text-slate-500 font-mono">v1.0 • Hackathon Edition</div>
      </header>

      {/* HERO PRINCIPAL */}
      <main className="flex-1 flex flex-col justify-center items-center px-4 py-10 relative overflow-hidden">
        {/* Background glows */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-purple-600/15 rounded-full blur-[140px] pointer-events-none" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 w-[400px] h-[400px] bg-cyan-500/10 rounded-full blur-[120px] pointer-events-none" />

        <div className="max-w-3xl w-full text-center z-10 space-y-6">
          {/* Logo grande centrado */}
          <div className="flex justify-center mb-2">
            <svg viewBox="0 0 420 95" className="h-20 md:h-28 w-auto overflow-visible">
              <defs>
                <linearGradient id="ghostGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#06B6D4" />
                  <stop offset="100%" stopColor="#3B82F6" />
                </linearGradient>
                <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>
              <g className="flying-ghost" transform="translate(95, 5)">
                <path
                  d="M 40,15 C 20,15 10,32 10,52 L 10,75 L 20,67 L 30,75 L 40,67 L 50,75 L 60,67 L 70,75 L 70,52 C 70,32 60,15 40,15 Z"
                  fill="url(#ghostGrad)"
                  filter="url(#glow)"
                />
                <circle className="blinking-eye" cx="30" cy="38" r="4" fill="#FFFFFF" />
                <circle className="blinking-eye" cx="50" cy="38" r="4" fill="#FFFFFF" />
              </g>
              <text x="248" y="58" fontSize="40" fontWeight="800" fill="#FFFFFF" fontFamily="monospace" textAnchor="middle">
                dev<tspan fill="#06B6D4">.ghost</tspan><tspan fill="#3B82F6">()</tspan>
              </text>
              <text x="248" y="78" fontSize="10" fontWeight="600" fill="#94A3B8" letterSpacing="2" textAnchor="middle">
                AUTONOMOUS REPO PARSER
              </text>
            </svg>
          </div>

          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300 text-xs font-semibold tracking-wide">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <span>AGENTE AUTÓNOMO DE ARQUITECTURA DE SOFTWARE</span>
          </div>

          {/* Título */}
          <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-slate-100 leading-tight">
            Entiende cualquier{' '}
            <span className="bg-gradient-to-r from-purple-400 via-cyan-400 to-blue-500 bg-clip-text text-transparent">
              Codebase
            </span>{' '}
            en segundos.
          </h1>

          {/* Subtítulo */}
          <p className="text-slate-400 text-base md:text-lg max-w-xl mx-auto leading-relaxed">
            Análisis profundo con IA: grafo de arquitectura, auditoría de código, documentación técnica,
            casos de uso UML e historias de usuario — todo automatizado.
          </p>

          {/* Repositorios de prueba */}
          <div className="pt-2 flex flex-wrap items-center justify-center gap-2 text-xs text-slate-400">
            <span className="font-mono text-slate-500">Prueba con:</span>
            {SAMPLE_REPOS.map((repo) => (
              <button
                key={repo.url}
                type="button"
                onClick={() => setRepoUrl(repo.url)}
                className={`px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 border text-slate-300 hover:text-cyan-400 transition-all ${
                  repo.highlight ? 'border-cyan-500/40 text-cyan-400' : 'border-slate-700/60'
                }`}
              >
                {repo.label}
              </button>
            ))}
          </div>

          {/* FORMULARIO PRINCIPAL */}
          <div className="pt-2 max-w-2xl mx-auto w-full">
            <div className="flex items-center gap-2 p-2 rounded-2xl bg-slate-900/90 border border-slate-700/80 focus-within:border-cyan-500 focus-within:ring-2 focus-within:ring-cyan-500/20 transition-all shadow-2xl shadow-purple-950/40">
              <input
                type="url"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                onKeyDown={handleKeyDown}
                maxLength={2048}
                placeholder="https://github.com/usuario/repositorio"
                className="w-full bg-transparent px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
                aria-label="URL del repositorio a analizar"
              />
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!isValid}
                aria-disabled={!isValid}
                className="bg-gradient-to-r from-purple-600 via-indigo-600 to-cyan-500 hover:from-purple-500 hover:to-cyan-400 text-white font-semibold text-sm px-6 py-2.5 rounded-xl transition-all shadow-lg shadow-purple-900/30 shrink-0 flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span>Analyze</span>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>
            </div>
          </div>

          {/* Features Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-8 text-left">
            <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-purple-500/40 transition-all">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center mb-3 text-purple-400">
                🧠
              </div>
              <h3 className="font-semibold text-slate-200 text-sm mb-1">Análisis Inteligente</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                5 sub-agentes de IA analizan en paralelo: AST, ER, auditoría de código, documentación y stack tecnológico.
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-cyan-500/40 transition-all">
              <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-3 text-cyan-400">
                📄
              </div>
              <h3 className="font-semibold text-slate-200 text-sm mb-1">Documentación Automática</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Genera C4, ADR, RBAC, plan de testing, casos de uso UML e historias de usuario con estándar IEEE.
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-blue-500/40 transition-all">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mb-3 text-blue-400">
                🔍
              </div>
              <h3 className="font-semibold text-slate-200 text-sm mb-1">Auditoría por Componente</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Inspección profunda de cada nodo: código fuente, calidad SOLID, vulnerabilidades y recomendaciones.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default InitialHeroState;
