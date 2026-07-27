import ReactMarkdown from 'react-markdown';
import { MermaidDiagram } from './MermaidDiagram';

interface MarkdownRendererProps {
  content: string;
}

/**
 * Splits content into alternating markdown, HTML table, and mermaid blocks.
 */
function splitContent(text: string): { type: 'markdown' | 'html' | 'mermaid'; content: string }[] {
  const parts: { type: 'markdown' | 'html' | 'mermaid'; content: string }[] = [];
  // Match HTML tables, HTML blocks (div, section, etc.), and mermaid code blocks
  const specialRegex = /(<table[\s\S]*?<\/table>|<div[\s\S]*?<\/div>|```mermaid\n([\s\S]*?)```)/gi;
  let lastIndex = 0;
  let match;

  while ((match = specialRegex.exec(text)) !== null) {
    // Add markdown before special block
    if (match.index > lastIndex) {
      const md = text.slice(lastIndex, match.index).trim();
      if (md) parts.push({ type: 'markdown', content: md });
    }

    if (match[0].startsWith('<table') || match[0].startsWith('<div')) {
      parts.push({ type: 'html', content: match[0] });
    } else {
      // Mermaid block — extract content between ```mermaid and ```
      const mermaidCode = match[2] || match[0].replace(/```mermaid\n?/, '').replace(/\n?```$/, '');
      parts.push({ type: 'mermaid', content: mermaidCode.trim() });
    }
    lastIndex = match.index + match[0].length;
  }

  // Add remaining markdown after last special block
  if (lastIndex < text.length) {
    const md = text.slice(lastIndex).trim();
    if (md) parts.push({ type: 'markdown', content: md });
  }

  // If no special blocks found, return everything as markdown
  if (parts.length === 0) {
    parts.push({ type: 'markdown', content: text });
  }

  return parts;
}

function normalizeMarkdown(raw: string): string {
  let text = raw;

  // Remove code fence wrappers if the entire content is wrapped
  text = text.replace(/^```(?:markdown|md)?\n?/i, '');
  text = text.replace(/\n?```\s*$/i, '');

  // FIX: Tables on a single line — split rows that are concatenated
  // Pattern: "| val1 | val2 | | val3 | val4 |" (double pipe = row separator)
  // Also handles: "| header1 | header2 || --- | --- || val1 | val2 |"
  text = text.replace(/\|\s*\|\s*(?=[|/\w])/g, '|\n|');

  // FIX: Separator rows jammed together with data rows
  // "| header |---|---|| data |" patterns
  text = text.replace(/\|(\s*---+\s*\|)+\s*\|/g, (match) => match.replace(/\|\s*\|/, '|\n|'));

  // FIX: If a line has many pipe groups that look like a table row repeated,
  // split it. Detect pattern like "| ... | | ... |" where || means new row
  text = text.split('\n').map(line => {
    // If line starts with | and has "| |" or "||" patterns (row concatenation)
    if (line.startsWith('|') && (line.includes('| |') || line.includes('||'))) {
      // Split on "| |" (row boundary) — but not on "| --- |" separator content
      const parts = line.split(/\|\s+\|(?!\s*-)/);
      if (parts.length > 2) {
        // Likely concatenated rows — reconstruct
        return parts.map(p => {
          const trimmed = p.trim();
          if (!trimmed.startsWith('|')) return '| ' + trimmed;
          return trimmed;
        }).filter(p => p.trim() !== '|' && p.trim() !== '').join('\n');
      }
    }
    return line;
  }).join('\n');

  // Ensure separator row (|---|) has its own line
  text = text.replace(/([^\n])((?:\|[\s:]*-{2,}[\s:]*)+\|)/g, '$1\n$2');
  text = text.replace(/((?:\|[\s:]*-{2,}[\s:]*)+\|)([^\n])/g, '$1\n$2');

  // Ensure blank line before headings
  text = text.replace(/([^\n])\n(#{1,6} )/g, '$1\n\n$2');

  // Ensure blank line before first table row (pipe after non-pipe text)
  text = text.replace(/([^|\n\-])\n(\|)/g, '$1\n\n$2');

  // Collapse excessive newlines
  text = text.replace(/\n{3,}/g, '\n\n');

  return text.trim();
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const normalized = normalizeMarkdown(content);
  const parts = splitContent(normalized);

  return (
    <div className="bg-white text-gray-800 p-6 rounded-xl border border-gray-200 shadow-sm space-y-1 overflow-x-auto">
      {parts.map((part, idx) => {
        if (part.type === 'html') {
          return (
            <div
              key={idx}
              className="my-4 overflow-x-auto rounded-lg border border-gray-200 shadow-sm [&_table]:min-w-full [&_table]:divide-y [&_table]:divide-gray-200 [&_table]:text-xs [&_thead]:bg-gray-50 [&_th]:px-4 [&_th]:py-2.5 [&_th]:text-left [&_th]:font-bold [&_th]:text-gray-700 [&_th]:uppercase [&_th]:tracking-wider [&_th]:text-[10px] [&_th]:border-b-2 [&_th]:border-gray-200 [&_td]:px-4 [&_td]:py-2 [&_td]:border-b [&_td]:border-gray-100 [&_td]:text-gray-600 [&_td]:text-xs [&_tr:hover]:bg-blue-50/50"
              dangerouslySetInnerHTML={{ __html: part.content }}
            />
          );
        }
        if (part.type === 'mermaid') {
          return (
            <div key={idx} className="my-4">
              <MermaidDiagram code={part.content} />
            </div>
          );
        }
        return (
          <ReactMarkdown key={idx} components={{
          h1: ({ children }) => (
            <h1 className="text-xl font-bold text-gray-900 border-b-2 border-blue-200 pb-3 mb-5 mt-2">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-bold text-gray-800 mt-7 mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-bold text-gray-700 mt-5 mb-2">{children}</h3>
          ),
          p: ({ children }) => (
            <p className="text-[13px] text-gray-600 leading-relaxed mb-3">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="space-y-1.5 mb-4 pl-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="space-y-1.5 mb-4 pl-5 list-decimal list-outside text-[13px] text-gray-700">{children}</ol>
          ),
          li: ({ children }) => {
            const text = String(children || '').toLowerCase();
            if (text.includes('crítica') || text.includes('alta') || text.includes('critical')) {
              return <li className="p-3 rounded-lg border-l-4 border-red-500 bg-red-50 text-[13px] text-gray-700 list-none">{children}</li>;
            }
            if (text.includes('media') || text.includes('medium') || text.includes('moderada')) {
              return <li className="p-3 rounded-lg border-l-4 border-yellow-500 bg-yellow-50 text-[13px] text-gray-700 list-none">{children}</li>;
            }
            if (text.includes('buena') || text.includes('positiv') || text.includes('✅') || text.includes('✔')) {
              return <li className="p-3 rounded-lg border-l-4 border-emerald-500 bg-emerald-50 text-[13px] text-gray-700 list-none">{children}</li>;
            }
            return (
              <li className="text-[13px] text-gray-600 flex items-start gap-2 list-none">
                <span className="text-blue-500 mt-0.5 shrink-0">▸</span>
                <span className="flex-1">{children}</span>
              </li>
            );
          },
          table: ({ children }) => (
            <div className="overflow-x-auto my-4 rounded-lg border border-gray-200 shadow-sm">
              <table className="min-w-full divide-y divide-gray-200 text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-gray-50">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="px-4 py-2.5 text-left font-bold text-gray-700 uppercase tracking-wider text-[10px] border-b-2 border-gray-200">{children}</th>
          ),
          td: ({ children }) => {
            const text = String(children || '').trim();
            if (text === 'PK') return <td className="px-4 py-2 border-b border-gray-100"><span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-bold text-[10px]">🔑 PK</span></td>;
            if (text === 'FK') return <td className="px-4 py-2 border-b border-gray-100"><span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-bold text-[10px]">🔗 FK</span></td>;
            if (text === 'Alta') return <td className="px-4 py-2 border-b border-gray-100"><span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-bold text-[10px]">✓ Alta</span></td>;
            if (text === 'Baja') return <td className="px-4 py-2 border-b border-gray-100"><span className="px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700 font-bold text-[10px]">⚠ Baja</span></td>;
            if (text === 'Nula') return <td className="px-4 py-2 border-b border-gray-100"><span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-bold text-[10px]">✗ Nula</span></td>;
            if (text === 'Sí' || text === 'Si') return <td className="px-4 py-2 border-b border-gray-100"><span className="text-emerald-600 font-semibold">✓ Sí</span></td>;
            if (text === 'No') return <td className="px-4 py-2 border-b border-gray-100"><span className="text-gray-400">— No</span></td>;
            // Color type names
            if (['integer', 'float', 'number'].some(t => text.toLowerCase() === t)) {
              return <td className="px-4 py-2 border-b border-gray-100 font-mono text-xs text-emerald-600">{text}</td>;
            }
            if (['string', 'varchar', 'text'].some(t => text.toLowerCase() === t)) {
              return <td className="px-4 py-2 border-b border-gray-100 font-mono text-xs text-violet-600">{text}</td>;
            }
            if (['boolean', 'bool'].some(t => text.toLowerCase() === t)) {
              return <td className="px-4 py-2 border-b border-gray-100 font-mono text-xs text-orange-600">{text}</td>;
            }
            if (['datetime', 'date', 'timestamp'].some(t => text.toLowerCase() === t)) {
              return <td className="px-4 py-2 border-b border-gray-100 font-mono text-xs text-cyan-600">{text}</td>;
            }
            if (text.toLowerCase() === 'enum') {
              return <td className="px-4 py-2 border-b border-gray-100 font-mono text-xs text-pink-600">{text}</td>;
            }
            return <td className="px-4 py-2 border-b border-gray-100 text-gray-600 text-xs">{children}</td>;
          },
          tr: ({ children }) => (
            <tr className="hover:bg-blue-50/50 transition-colors">{children}</tr>
          ),
          pre: ({ children }) => (
            <div className="my-4 rounded-lg overflow-hidden border border-gray-300">
              <div className="bg-gray-800 px-3 py-1.5 text-[10px] text-gray-400 font-mono border-b border-gray-700 flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
                <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
                <span className="w-2.5 h-2.5 rounded-full bg-green-400" />
                <span className="ml-2">código</span>
              </div>
              <pre className="bg-[#0d1117] p-4 overflow-x-auto max-w-full">
                {children}
              </pre>
            </div>
          ),
          code: ({ children, className }) => {
            const text = String(children || '');
            // Detect if this is a code block (inside <pre>) vs inline code
            const isBlock = className?.startsWith('language-') || text.includes('\n');
            if (isBlock) {
              return <code className="text-green-300 text-xs font-mono leading-relaxed whitespace-pre block">{children}</code>;
            }
            return <code className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-[11px] font-mono border border-gray-200">{children}</code>;
          },
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-blue-300 pl-4 py-2 my-4 bg-blue-50 rounded-r-lg">
              {children}
            </blockquote>
          ),
          strong: ({ children }) => (
            <strong className="font-bold text-gray-900">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="text-gray-500 italic">{children}</em>
          ),
          hr: () => <hr className="my-6 border-gray-200" />,
        }}>
          {part.content}
        </ReactMarkdown>
        );
      })}
    </div>
  );
}
