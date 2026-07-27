/**
 * Logo component — dev.ghost() isotipo (Opción 2)
 * Renders the brand mark with a subtle floating (levitation) CSS animation.
 */

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      {/* Ghost isotipo with float animation */}
      <div className="animate-ghost-float">
        <svg
          width="32"
          height="32"
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          {/* Ghost body */}
          <path
            d="M16 4C10.477 4 6 8.477 6 14v10c0 0.5 0.5 1 1 0.5l2-2 2 2 2-2 2 2 2-2 2 2 2-2 2 2c0.5 0.5 1 0 1-0.5V14c0-5.523-4.477-10-10-10z"
            fill="url(#ghost-gradient)"
            opacity="0.95"
          />
          {/* Left eye */}
          <circle cx="12.5" cy="14" r="2" fill="#1e293b" />
          {/* Right eye */}
          <circle cx="19.5" cy="14" r="2" fill="#1e293b" />
          {/* Code brackets < /> */}
          <path
            d="M11 19l-2 1.5 2 1.5M21 19l2 1.5-2 1.5M14.5 23l3-5"
            stroke="#1e293b"
            strokeWidth="1.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.7"
          />
          <defs>
            <linearGradient id="ghost-gradient" x1="6" y1="4" x2="26" y2="28" gradientUnits="userSpaceOnUse">
              <stop stopColor="#818cf8" />
              <stop offset="1" stopColor="#6366f1" />
            </linearGradient>
          </defs>
        </svg>
      </div>

      {/* Logotype */}
      <span className="text-lg font-bold text-white tracking-tight">
        <span className="text-indigo-400">dev</span>
        <span className="text-gray-400">.</span>
        <span className="text-white">ghost</span>
        <span className="text-gray-500">()</span>
      </span>

      {/* ghostFloat keyframe animation — injected via style tag for portability */}
      <style>{`
        @keyframes ghost-float {
          0%, 100% {
            transform: translateY(0px);
          }
          50% {
            transform: translateY(-3px);
          }
        }
        .animate-ghost-float {
          animation: ghost-float 3s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
