export function GhostLoader() {
  return (
    <div className="relative flex items-center justify-center p-6">
      {/* Resplandor de Fondo (Glow Effect) */}
      <div className="absolute w-32 h-32 bg-cyan-500/20 rounded-full blur-2xl animate-pulse" />

      <svg
        viewBox="0 0 120 120"
        className="w-28 h-28 overflow-visible z-10"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="ghostBodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#06B6D4" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <radialGradient id="shadowGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(0,0,0,0.5)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </radialGradient>
        </defs>

        <style>{`
          @keyframes ghostFloat {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
          }
          .animate-ghost { animation: ghostFloat 3s ease-in-out infinite; }

          @keyframes eyeMove {
            0%, 100%, 80% { transform: translateX(0px); }
            20%, 35% { transform: translateX(-4px); }
            50%, 65% { transform: translateX(4px); }
          }
          .animate-eyes { animation: eyeMove 5s ease-in-out infinite; }

          @keyframes eyeWink {
            0%, 90%, 100% { transform: scaleY(1); }
            95% { transform: scaleY(0.1); }
          }
          .animate-wink { transform-origin: center; animation: eyeWink 4s ease-in-out infinite; }

          @keyframes particleFly {
            0% { transform: translateY(0) scale(0); opacity: 0; }
            50% { opacity: 1; }
            100% { transform: translateY(-20px) scale(1.2); opacity: 0; }
          }
          .particle-1 { animation: particleFly 2s infinite 0.2s ease-out; }
          .particle-2 { animation: particleFly 2.5s infinite 0.8s ease-out; }
          .particle-3 { animation: particleFly 2.2s infinite 1.4s ease-out; }

          @keyframes shadowScale {
            0%, 100% { transform: scale(1); opacity: 0.6; }
            50% { transform: scale(0.7); opacity: 0.3; }
          }
          .animate-shadow { transform-origin: center; animation: shadowScale 3s ease-in-out infinite; }
        `}</style>

        {/* Sombra en el Suelo */}
        <ellipse cx="60" cy="105" rx="24" ry="6" fill="url(#shadowGrad)" className="animate-shadow" />

        {/* CUERPO PRINCIPAL DEL FANTASMA */}
        <g className="animate-ghost">
          <path
            d="M 60,20 C 35,20 20,40 20,68 L 20,92 L 30,83 L 40,92 L 50,83 L 60,92 L 70,83 L 80,92 L 90,83 L 100,92 L 100,68 C 100,40 85,20 60,20 Z"
            fill="url(#ghostBodyGrad)"
          />

          {/* GRUPO DE OJOS */}
          <g className="animate-eyes">
            <circle cx="46" cy="50" r="5.5" fill="#FFFFFF" />
            <g className="animate-wink">
              <circle cx="74" cy="50" r="5.5" fill="#FFFFFF" />
            </g>
          </g>

          {/* Mejillas kawaii */}
          <circle cx="38" cy="58" r="3.5" fill="#FF77A9" opacity="0.3" />
          <circle cx="82" cy="58" r="3.5" fill="#FF77A9" opacity="0.3" />

          {/* PARTÍCULAS DE CÓDIGO */}
          <text x="10" y="40" fill="#06B6D4" fontSize="10" fontFamily="monospace" className="particle-1">{'</>'}</text>
          <text x="95" y="45" fill="#3B82F6" fontSize="12" fontFamily="monospace" className="particle-2">{'{}'}</text>
          <text x="15" y="75" fill="#A855F7" fontSize="10" fontFamily="monospace" className="particle-3">01</text>
        </g>
      </svg>
    </div>
  );
}
