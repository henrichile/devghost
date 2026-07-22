import type { AnalysisResponse } from '../types';
import { CodeFlowGraph } from './CodeFlowGraph';
import { ERDatabaseGraph } from './ERDatabaseGraph';

interface TabViewProps {
  activeTab: 'codeflow' | 'er';
  onTabChange: (tab: 'codeflow' | 'er') => void;
  response: AnalysisResponse;
}

export function TabView({ activeTab, onTabChange, response }: TabViewProps) {
  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div
        className="flex border-b border-gray-200"
        role="tablist"
        aria-label="Graph views"
      >
        <button
          role="tab"
          id="tab-codeflow"
          aria-selected={activeTab === 'codeflow'}
          aria-controls="tabpanel-codeflow"
          className={`px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
            activeTab === 'codeflow'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700 hover:border-b-2 hover:border-gray-300'
          }`}
          onClick={() => onTabChange('codeflow')}
        >
          Code Flow Graph
        </button>
        <button
          role="tab"
          id="tab-er"
          aria-selected={activeTab === 'er'}
          aria-controls="tabpanel-er"
          className={`px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
            activeTab === 'er'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700 hover:border-b-2 hover:border-gray-300'
          }`}
          onClick={() => onTabChange('er')}
        >
          ER Database Graph
        </button>
      </div>

      {activeTab === 'codeflow' && (
        <div
          role="tabpanel"
          id="tabpanel-codeflow"
          aria-labelledby="tab-codeflow"
          className="flex-1 min-h-0"
        >
          <CodeFlowGraph data={response.codeFlow} />
        </div>
      )}

      {activeTab === 'er' && (
        <div
          role="tabpanel"
          id="tabpanel-er"
          aria-labelledby="tab-er"
          className="flex-1 min-h-0"
        >
          {response.erModel ? (
            <ERDatabaseGraph
              entities={response.erModel.entities}
              relations={response.erModel.relations}
            />
          ) : (
            <div className="flex items-center justify-center h-full p-8 text-gray-500">
              No ER model data available.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
