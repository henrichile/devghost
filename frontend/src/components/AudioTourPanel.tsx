import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Square } from "lucide-react";

interface AudioTourPanelProps {
  summary: string;
}

type SpeechState = "idle" | "speaking";

/**
 * Busca una voz en español disponible en el navegador.
 * Prioriza es-ES, luego cualquier es-*.
 */
function findSpanishVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();

  // Priorizar es-ES
  const esES = voices.find((v) => v.lang === "es-ES");
  if (esES) return esES;

  // Cualquier variante de español
  const esAny = voices.find((v) => v.lang.startsWith("es"));
  if (esAny) return esAny;

  return null;
}

export function AudioTourPanel({ summary }: AudioTourPanelProps) {
  const [state, setState] = useState<SpeechState>("idle");
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const [voicesLoaded, setVoicesLoaded] = useState(false);

  const isSpeechAvailable =
    typeof window !== "undefined" && "speechSynthesis" in window;

  // Las voces pueden cargarse de forma asíncrona
  useEffect(() => {
    if (!isSpeechAvailable) return;

    const handleVoicesChanged = () => setVoicesLoaded(true);

    // Algunas veces ya están cargadas
    if (window.speechSynthesis.getVoices().length > 0) {
      setVoicesLoaded(true);
    }

    window.speechSynthesis.addEventListener("voiceschanged", handleVoicesChanged);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", handleVoicesChanged);
    };
  }, [isSpeechAvailable]);

  const handlePlay = useCallback(() => {
    if (!isSpeechAvailable || !summary) return;

    const utterance = new SpeechSynthesisUtterance(summary);
    utteranceRef.current = utterance;

    // Configurar idioma español
    utterance.lang = "es-ES";

    // Intentar usar una voz en español
    if (voicesLoaded) {
      const spanishVoice = findSpanishVoice();
      if (spanishVoice) {
        utterance.voice = spanishVoice;
      }
    }

    utterance.onend = () => {
      setState("idle");
    };

    utterance.onerror = () => {
      setState("idle");
    };

    window.speechSynthesis.speak(utterance);
    setState("speaking");
  }, [isSpeechAvailable, summary, voicesLoaded]);

  const handleStop = useCallback(() => {
    if (!isSpeechAvailable) return;

    window.speechSynthesis.cancel();
    setState("idle");
  }, [isSpeechAvailable]);

  // Limpiar al desmontar
  useEffect(() => {
    return () => {
      if (isSpeechAvailable) {
        window.speechSynthesis.cancel();
      }
    };
  }, [isSpeechAvailable]);

  return (
    <div className="p-4 border-t border-gray-200">
      <h2 className="text-lg font-semibold mb-2">Audio Tour</h2>
      <p className="text-sm text-gray-700 mb-4 whitespace-pre-wrap">
        {summary}
      </p>
      <div className="relative inline-block">
        {state === "idle" ? (
          <button
            onClick={handlePlay}
            disabled={!isSpeechAvailable || !summary}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Reproducir narración"
            title={
              !isSpeechAvailable
                ? "La síntesis de voz no está disponible en este navegador"
                : undefined
            }
          >
            <Play size={16} />
            Reproducir
          </button>
        ) : (
          <button
            onClick={handleStop}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
            aria-label="Detener narración"
          >
            <Square size={16} />
            Detener
          </button>
        )}
        {!isSpeechAvailable && (
          <p className="text-xs text-amber-600 mt-1">
            La síntesis de voz no está disponible en este navegador.
          </p>
        )}
      </div>
    </div>
  );
}
