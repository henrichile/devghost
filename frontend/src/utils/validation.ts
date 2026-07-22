/**
 * Validates whether a given input string is a valid URL for analysis.
 *
 * Returns true only if the input is a non-empty string (after trimming)
 * that starts with "http://" or "https://".
 */
export function isValidUrl(input: string): boolean {
  const trimmed = input.trim();

  if (trimmed.length === 0) {
    return false;
  }

  return trimmed.startsWith("http://") || trimmed.startsWith("https://");
}
