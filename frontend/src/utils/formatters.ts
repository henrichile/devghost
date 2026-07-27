/**
 * Utility functions for formatting elapsed time, duration, and message truncation.
 */

export function formatElapsedTime(elapsedMs: number): string {
  const totalSeconds = Math.floor(elapsedMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `+${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export function formatDuration(durationMs: number): string {
  const totalSeconds = durationMs / 1000;
  const wholeSeconds = Math.floor(totalSeconds);
  const tenths = Math.floor((totalSeconds - wholeSeconds) * 10);
  return `${wholeSeconds}.${tenths}s`;
}

export function truncateMessage(message: string): string {
  if (message.length > 200) {
    return message.slice(0, 200) + '\u2026';
  }
  return message;
}
