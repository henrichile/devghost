import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

interface MermaidDiagramProps {
  code: string;
}

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
    curve: 'basis',
  },
});

let renderCount = 0;

export function MermaidDiagram({ code }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svgContent, setSvgContent] = useState<string>('');

  useEffect(() => {
    if (!code || !containerRef.current) return;

    // Sanitize mermaid code: fix common LLM syntax errors
    let sanitized = code;
    // Remove ALL parentheses inside square bracket labels [...]
    // This is the #1 cause of Mermaid parse errors from LLM output
    sanitized = sanitized.replace(/\[([^\]]*)\]/g, (_match, content) => {
      return '[' + content.replace(/[()]/g, '') + ']';
    });
    // Also clean curly brace labels {...}
    sanitized = sanitized.replace(/\{([^}]*)\}/g, (_match, content) => {
      return '{' + content.replace(/[()]/g, '') + '}';
    });
    // Fix quotes
    sanitized = sanitized.replace(/"/g, "'");

    const renderDiagram = async () => {
      try {
        setError(null);
        const id = `mermaid-diagram-${++renderCount}`;
        const { svg } = await mermaid.render(id, sanitized);
        setSvgContent(svg);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al renderizar el diagrama');
        setSvgContent('');
      }
    };

    renderDiagram();
  }, [code]);

  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
          <p className="text-xs text-red-600">⚠️ Error de sintaxis Mermaid: {error}</p>
        </div>
        <pre className="whitespace-pre-wrap text-xs text-gray-600 font-mono bg-gray-50 p-4 rounded-lg border">
          {code}
        </pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full overflow-auto p-4 bg-white rounded-xl border border-gray-200 shadow-sm"
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  );
}
