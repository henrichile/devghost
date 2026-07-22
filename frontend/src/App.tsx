import { useState } from 'react';
import type { AnalysisResponse } from './types';
import { analyzeRepo } from './services/api';
import { Header } from './components/Header';
import { TabView } from './components/TabView';
import { AudioTourPanel } from './components/AudioTourPanel';
import { ErrorBanner } from './components/ErrorBanner';
import { LoadingIndicator } from './components/LoadingIndicator';

function App() {
  const [repoUrl, setRepoUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'codeflow' | 'er'>('codeflow');

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await analyzeRepo(repoUrl);
      setResponse(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        onAnalyze={handleAnalyze}
        loading={loading}
        repoUrl={repoUrl}
        onUrlChange={setRepoUrl}
      />
      {loading && <LoadingIndicator />}
      {error && <ErrorBanner message={error} />}
      {response && (
        <TabView
          activeTab={activeTab}
          onTabChange={setActiveTab}
          response={response}
        />
      )}
      {response?.summary && <AudioTourPanel summary={response.summary} />}
    </div>
  );
}

export default App;
