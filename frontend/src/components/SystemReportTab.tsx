import { MarkdownRenderer } from './MarkdownRenderer';

interface TechStackEntry {
  name: string;
  category: string;
  description?: string;
}

interface SystemReportData {
  tech_stack: { entries: TechStackEntry[] };
  setup_instructions: string;
  project_description: string;
  could_not_determine?: boolean;
}

interface SystemReportTabProps {
  data: SystemReportData | null | undefined;
}

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
  language: { label: 'Lenguajes', color: 'bg-purple-500/10 border-purple-500/30 text-purple-300' },
  framework: { label: 'Frameworks', color: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300' },
  database: { label: 'Bases de Datos', color: 'bg-amber-500/10 border-amber-500/30 text-amber-300' },
  infrastructure: { label: 'Infraestructura', color: 'bg-green-500/10 border-green-500/30 text-green-300' },
};

function groupByCategory(entries: TechStackEntry[]): Record<string, TechStackEntry[]> {
  const grouped: Record<string, TechStackEntry[]> = {};
  for (const entry of entries) {
    if (!grouped[entry.category]) grouped[entry.category] = [];
    grouped[entry.category].push(entry);
  }
  return grouped;
}

export function SystemReportTab({ data }: SystemReportTabProps) {
  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        <div className="text-center space-y-2">
          <div className="text-3xl">📊</div>
          <p>No se pudo generar el reporte del sistema.</p>
          <p className="text-xs text-slate-600">El agente System Reporter no produjo resultados.</p>
        </div>
      </div>
    );
  }

  if (data.could_not_determine) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        <div className="text-center space-y-2">
          <div className="text-3xl">🔍</div>
          <p>No se detectó el stack tecnológico.</p>
          <p className="text-xs text-slate-600">No se encontraron archivos de configuración reconocibles.</p>
        </div>
      </div>
    );
  }

  const grouped = groupByCategory(data.tech_stack?.entries || []);
  const categories = Object.keys(grouped).filter(cat => grouped[cat].length > 0);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-8">
      {/* Technology Stack */}
      {categories.length > 0 && (
        <section>
          <h2 className="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            Stack Tecnológico
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {categories.map(cat => (
              <div key={cat} className="rounded-xl border border-white/[0.06] bg-[#0F1420] p-4">
                <h3 className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  {CATEGORY_LABELS[cat]?.label || cat}
                </h3>
                <div className="flex flex-wrap gap-2">
                  {grouped[cat].map(entry => (
                    <span
                      key={entry.name}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium border ${CATEGORY_LABELS[cat]?.color || 'bg-slate-800 border-slate-700 text-slate-300'}`}
                      title={entry.description}
                    >
                      {entry.name}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Project Description */}
      {data.project_description && (
        <section>
          <h2 className="text-sm font-bold text-slate-200 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-purple-400" />
            Descripción del Proyecto
          </h2>
          <div className="rounded-xl border border-white/[0.06] bg-[#0F1420] p-4">
            <p className="text-[13px] text-slate-400 leading-relaxed">{data.project_description}</p>
          </div>
        </section>
      )}

      {/* Setup Instructions */}
      {data.setup_instructions && (
        <section>
          <h2 className="text-sm font-bold text-slate-200 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            Cómo Ejecutar
          </h2>
          <MarkdownRenderer content={data.setup_instructions} />
        </section>
      )}
    </div>
  );
}
