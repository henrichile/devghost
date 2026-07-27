import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Square } from "lucide-react";
import { selectRepresentativeNodes } from "../hooks/useHighlightEngine";
import { useGraphStore } from "../store/useGraphStore";

interface AudioTourPanelProps {
  summary: string;
}

type SpeechState = "idle" | "speaking";

function findSpanishVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  // Prefer high-quality voices
  const premium = voices.find((v) => v.lang.startsWith("es") && v.name.toLowerCase().includes("google"));
  if (premium) return premium;
  const esES = voices.find((v) => v.lang === "es-ES");
  if (esES) return esES;
  const esAny = voices.find((v) => v.lang.startsWith("es"));
  if (esAny) return esAny;
  return null;
}

export function AudioTourPanel({ summary }: AudioTourPanelProps) {
  const [state, setState] = useState<SpeechState>("idle");
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const [voicesLoaded, setVoicesLoaded] = useState(false);
  const sentenceIndexRef = useRef(0);
  const representativeNodesRef = useRef<{ id: string }[]>([]);

  const isSpeechAvailable = typeof window !== "undefined" && "speechSynthesis" in window;

  const nodes = useGraphStore((s) => s.nodes);
  const startTour = useGraphStore((s) => s.startTour);
  const stopTour = useGraphStore((s) => s.stopTour);
  const setHighlightedNode = useGraphStore((s) => s.setHighlightedNode);

  useEffect(() => {
    if (!isSpeechAvailable) return;
    const handleVoicesChanged = () => setVoicesLoaded(true);
    if (window.speechSynthesis.getVoices().length > 0) setVoicesLoaded(true);
    window.speechSynthesis.addEventListener("voiceschanged", handleVoicesChanged);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", handleVoicesChanged);
  }, [isSpeechAvailable]);

  const handlePlay = useCallback(() => {
    if (!isSpeechAvailable || !summary) return;

    // Split summary into sentences for sync
    const sentences = summary.split(/(?<=[.!?])\s+/).filter(Boolean);
    const repNodes = selectRepresentativeNodes(nodes);
    representativeNodesRef.current = repNodes;
    sentenceIndexRef.current = 0;

    const utterance = new SpeechSynthesisUtterance(summary);
    utteranceRef.current = utterance;
    utterance.lang = "es-ES";
    utterance.rate = 0.9; // Slightly slower for clarity
    utterance.pitch = 1.0;

    if (voicesLoaded) {
      const spanishVoice = findSpanishVoice();
      if (spanishVoice) utterance.voice = spanishVoice;
    }

    // Sync highlighting with sentence boundaries
    utterance.onboundary = (event) => {
      if (event.name === "sentence" && repNodes.length > 0) {
        sentenceIndexRef.current++;
        // Map sentence index to node index proportionally
        const nodeIdx = Math.min(
          Math.floor((sentenceIndexRef.current / sentences.length) * repNodes.length),
          repNodes.length - 1
        );
        setHighlightedNode(repNodes[nodeIdx].id);
      }
    };

    utterance.onend = () => {
      setState("idle");
      stopTour();
      setHighlightedNode(null);
    };

    utterance.onerror = () => {
      setState("idle");
      stopTour();
      setHighlightedNode(null);
    };

    // Start
    window.speechSynthesis.cancel(); // Clear any previous
    window.speechSynthesis.speak(utterance);
    setState("speaking");

    // Highlight first node immediately
    if (repNodes.length > 0) {
      setHighlightedNode(repNodes[0].id);
    }
    startTour(repNodes.map((n) => n.id));
  }, [isSpeechAvailable, summary, voicesLoaded, nodes, startTour, stopTour, setHighlightedNode]);

  const handleStop = useCallback(() => {
    if (!isSpeechAvailable) return;
    window.speechSynthesis.cancel();
    setState("idle");
    stopTour();
    setHighlightedNode(null);
  }, [isSpeechAvailable, stopTour, setHighlightedNode]);

  useEffect(() => {
    return () => {
      if (isSpeechAvailable) window.speechSynthesis.cancel();
    };
  }, [isSpeechAvailable]);

  return (
    <div className="inline-flex">
      {state === "idle" ? (
        <button
          onClick={handlePlay}
          disabled={!isSpeechAvailable || !summary}
          className="flex items-center gap-2 px-4 py-1.5 bg-transparent border border-cyan-500/50 text-cyan-400 text-[11px] font-medium rounded-lg hover:bg-cyan-500/10 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          aria-label="Reproducir narración"
        >
          <Play size={12} />
          Escuchar Audio Tour
        </button>
      ) : (
        <button
          onClick={handleStop}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-xs font-semibold rounded-lg hover:bg-red-500 transition-colors"
          aria-label="Detener narración"
        >
          <Square size={14} />
          Detener
        </button>
      )}
    </div>
  );
}
