import { useState, useEffect } from 'react';
import { GhostLoader } from './GhostLoader';

const STEPS = [
  'Clonando repositorio y analizando AST...',
  'Extrayendo modelo de datos ER y tablas...',
  'Generando análisis de arquitectura con IA...',
  'Generando documentación (C4, ADR, RBAC, Testing)...',
  'Auditando componentes y generando descripciones...',
];

export function LoadingIndicator() {
  const [elapsed, setElapsed] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 100);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  // Advance steps based on elapsed time — slower progression
  useEffect(() => {
    if (elapsed < 5000) setCurrentStep(0);
    else if (elapsed < 12000) setCurrentStep(1);
    else if (elapsed < 25000) setCurrentStep(2);
    else if (elapsed < 45000) setCurrentStep(3);
    else setCurrentStep(4);
  }, [elapsed]);

  // Smooth progress that slows down near the end (never hits 100%)
  const progress = Math.min(95, (1 - Math.exp(-elapsed / 60000)) * 100);
  const elapsedSec = Math.floor(elapsed / 1000);

  return (
    <div className="fixed inset-0 bg-[#060911] z-50 flex flex-col items-center justify-center px-4">
      {/* Background glows */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-purple-600/8 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/3 left-1/2 -translate-x-1/2 w-[300px] h-[300px] bg-cyan-500/6 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative z-10 max-w-md w-full space-y-8 text-center">
        {/* Ghost animation */}
        <div className="flex justify-center">
          <GhostLoader />
        </div>

        {/* Title */}
        <h2 className="text-xl font-bold text-slate-100">Analizando repositorio</h2>
        <p className="text-[13px] text-slate-500 leading-relaxed">
          Este proceso puede tomar entre 2 y 5 minutos dependiendo del tamaño del repositorio. Estamos clonando, analizando la arquitectura, generando documentación y auditando cada componente con IA.
        </p>

        {/* Progress bar */}
        <div className="w-full">
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden border border-slate-700/30">
            <div
              className="h-full bg-gradient-to-r from-purple-500 via-cyan-400 to-blue-500 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-xs text-slate-500">
            <span>{Math.round(progress)}%</span>
            <span>{elapsedSec}s transcurridos</span>
          </div>
        </div>

        {/* Steps */}
        <div className="space-y-2.5 text-left">
          {STEPS.map((step, idx) => {
            const isActive = idx === currentStep;
            const isDone = idx < currentStep;
            return (
              <div
                key={idx}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border transition-all duration-500 ${
                  isActive
                    ? 'bg-slate-800/60 border-cyan-500/30 text-cyan-300'
                    : isDone
                    ? 'bg-slate-900/30 border-slate-800/20 text-slate-500'
                    : 'bg-slate-900/20 border-slate-800/10 text-slate-600'
                }`}
              >
                <div className="shrink-0">
                  {isDone ? (
                    <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isActive ? (
                    <div className="w-5 h-5 flex items-center justify-center">
                      <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 flex items-center justify-center">
                      <div className="w-2 h-2 rounded-full bg-slate-700" />
                    </div>
                  )}
                </div>
                <span className="text-sm font-medium">{step}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
