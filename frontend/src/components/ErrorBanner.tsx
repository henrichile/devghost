import { AlertCircle } from "lucide-react";

interface ErrorBannerProps {
  message: string;
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div
      className="flex items-start gap-3 bg-red-50 border border-red-300 text-red-800 px-4 py-3 rounded-lg mx-4 my-4"
      role="alert"
    >
      <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 shrink-0" aria-hidden="true" />
      <p className="text-sm font-medium">{message}</p>
    </div>
  );
}
