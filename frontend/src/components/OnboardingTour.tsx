import { useState, useEffect } from 'react';

const TOUR_STORAGE_KEY = 'devghost-tour-completed';

interface TourStep {
  title: string;
  description: string;
  icon: string;
  highlight: string; // CSS selector hint (visual only)
}

const TOUR_STEPS: TourStep[] = [
  {
    title: 'Grafo de Arquitectura',
    description: 'Explora el mapa interactivo de componentes. Haz click en cualquier nodo para ver su detalle, código fuente y auditoría.',
    icon: '🏗️',
    highlight: 'codeflow',
  },
  {
    title: 'Panel de Inspección',
    description: 'Al seleccionar un nodo, verás sus métodos, dependencias y un reporte de auditoría con calidad SOLID y vulnerabilidades.',
    icon: '🔍',
    highlight: 'inspection',
  },
  {
    title: 'Modelo ER',
    description: 'Visualiza las tablas, entidades y relaciones de base de datos detectadas automáticamente desde el código.',
    icon: '🗄️',
    highlight: 'er',
  },
  {
    title: 'Documentación Técnica',
    description: 'Accede a C4, ADR, RBAC, Testing, Casos de Uso UML y Análisis de Clases — todo generado con IA.',
    icon: '📄',
    highlight: 'docs',
  },
  {
    title: 'System Report',
    description: 'Revisa el stack tecnológico detectado con instrucciones de instalación y descripción del proyecto.',
    icon: '⚙️',
    highlight: 'system',
  },
];

export function OnboardingTour() {
  const [isVisible, setIsVisible] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    const completed = localStorage.getItem(TOUR_STORAGE_KEY);
    if (!completed) {
      // Show tour after a brief delay for the dashboard to render
      const timer = setTimeout(() => setIsVisible(true), 1500);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleNext = () => {
    if (currentStep < TOUR_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleClose();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleClose = () => {
    setIsVisible(false);
    localStorage.setItem(TOUR_STORAGE_KEY, 'true');
  };

  const handleNeverShow = () => {
    setIsVisible(false);
    localStorage.setItem(TOUR_STORAGE_KEY, 'never');
  };

  if (!isVisible) return null;

  const step = TOUR_STEPS[currentStep];
  const isLast = currentStep === TOUR_STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-[#0F1420] border border-white/[0.08] rounded-2xl shadow-2xl overflow-hidden">
        {/* Header with progress */}
        <div className="px-6 pt-5 pb-3">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400">
              Tour del Sistema — Paso {currentStep + 1}/{TOUR_STEPS.length}
            </span>
            <button
              onClick={handleClose}
              className="w-6 h-6 flex items-center justify-center rounded-full text-slate-500 hover:text-white hover:bg-white/10 transition-colors text-xs"
            >
              ✕
            </button>
          </div>
          {/* Progress bar */}
          <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-500 to-cyan-400 rounded-full transition-all duration-300"
              style={{ width: `${((currentStep + 1) / TOUR_STEPS.length) * 100}%` }}
            />
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-cyan-500/20 border border-purple-500/20 flex items-center justify-center text-2xl shrink-0">
              {step.icon}
            </div>
            <div>
              <h3 className="text-[15px] font-bold text-white mb-2">{step.title}</h3>
              <p className="text-[13px] text-slate-400 leading-relaxed">{step.description}</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-white/[0.06] flex items-center justify-between">
          <button
            onClick={handleNeverShow}
            className="text-[11px] text-slate-600 hover:text-slate-400 transition-colors"
          >
            No mostrar de nuevo
          </button>
          <div className="flex items-center gap-2">
            {currentStep > 0 && (
              <button
                onClick={handlePrev}
                className="px-3 py-1.5 text-[12px] font-medium rounded-lg border border-slate-700 text-slate-300 hover:bg-white/5 transition-colors"
              >
                ← Anterior
              </button>
            )}
            <button
              onClick={handleNext}
              className="px-4 py-1.5 text-[12px] font-semibold rounded-lg bg-gradient-to-r from-purple-600 to-cyan-500 text-white hover:from-purple-500 hover:to-cyan-400 transition-all"
            >
              {isLast ? '✓ Finalizar' : 'Siguiente →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
