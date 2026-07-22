import { Search } from "lucide-react";
import { isValidUrl } from "../utils/validation";

interface HeaderProps {
  onAnalyze: (url: string) => void;
  loading: boolean;
  repoUrl: string;
  onUrlChange: (url: string) => void;
}

export function Header({ onAnalyze, loading, repoUrl, onUrlChange }: HeaderProps) {
  const isDisabled = !isValidUrl(repoUrl) || loading;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isDisabled) {
      onAnalyze(repoUrl);
    }
  }

  return (
    <header className="w-full bg-gray-900 border-b border-gray-700 px-6 py-4">
      <form onSubmit={handleSubmit} className="flex items-center gap-3 max-w-4xl mx-auto">
        <div className="flex-1 relative">
          <input
            type="text"
            value={repoUrl}
            onChange={(e) => onUrlChange(e.target.value)}
            maxLength={2048}
            placeholder="https://github.com/user/repo"
            className="w-full rounded-md border border-gray-600 bg-gray-800 px-4 py-2 text-sm text-gray-100 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            aria-label="Repository URL"
          />
        </div>
        <button
          type="submit"
          disabled={isDisabled}
          className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Search className="h-4 w-4" />
          Analyze
        </button>
      </form>
    </header>
  );
}
