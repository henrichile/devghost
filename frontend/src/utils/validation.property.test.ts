import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { isValidUrl } from './validation';

/**
 * Property 1: URL validation rejects all non-HTTP(S) strings
 *
 * For any string that is either empty, composed entirely of whitespace,
 * or does not begin with "http://" or "https://", the URL validation function
 * SHALL return false, and for any non-empty string that begins with "http://"
 * or "https://", the validation function SHALL return true.
 *
 * **Validates: Requirements 3.2**
 */
describe('Property 1: URL validation rejects all non-HTTP(S) strings', () => {
  it('returns false for empty strings', () => {
    fc.assert(
      fc.property(fc.constant(''), (input) => {
        expect(isValidUrl(input)).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it('returns false for whitespace-only strings', () => {
    fc.assert(
      fc.property(
        fc
          .array(fc.constantFrom(' ', '\t', '\n', '\r'), { minLength: 1, maxLength: 50 })
          .map((chars) => chars.join('')),
        (input) => {
          expect(isValidUrl(input)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('returns false for arbitrary strings not starting with http:// or https://', () => {
    fc.assert(
      fc.property(
        fc.string().filter((s) => {
          const trimmed = s.trim();
          return (
            trimmed.length > 0 &&
            !trimmed.startsWith('http://') &&
            !trimmed.startsWith('https://')
          );
        }),
        (input) => {
          expect(isValidUrl(input)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('returns true for any string starting with http://', () => {
    fc.assert(
      fc.property(fc.string(), (suffix) => {
        const input = `http://${suffix}`;
        expect(isValidUrl(input)).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it('returns true for any string starting with https://', () => {
    fc.assert(
      fc.property(fc.string(), (suffix) => {
        const input = `https://${suffix}`;
        expect(isValidUrl(input)).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it('returns true for http(s) URLs with leading whitespace (trim behavior)', () => {
    fc.assert(
      fc.property(
        fc
          .array(fc.constantFrom(' ', '\t', '\n', '\r'), { minLength: 0, maxLength: 10 })
          .map((chars) => chars.join('')),
        fc.constantFrom('http://', 'https://'),
        fc.string(),
        (whitespace, protocol, suffix) => {
          const input = `${whitespace}${protocol}${suffix}`;
          expect(isValidUrl(input)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});
