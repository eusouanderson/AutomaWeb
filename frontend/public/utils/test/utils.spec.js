import { describe, expect, it } from 'vitest';
import { escapeHtml, truncate } from '../helpers.js';
import { isValidUrl, requiredText } from '../validators.js';

describe('validators', () => {
  it('validates required text with min chars', () => {
    expect(requiredText('ab', 2)).toBe(true);
    expect(requiredText('a', 2)).toBe(false);
  });

  it('validates URL format', () => {
    expect(isValidUrl('https://example.com')).toBe(true);
    expect(isValidUrl('ftp://example.com')).toBe(false);
    expect(isValidUrl('abc')).toBe(false);
  });
});

describe('helpers', () => {
  it('escapes html special chars', () => {
    expect(escapeHtml('<div>"x"</div>')).toBe('&lt;div&gt;&quot;x&quot;&lt;/div&gt;');
  });

  it('truncates long strings', () => {
    expect(truncate('abcdef', 3)).toBe('abc...');
    expect(truncate('abc', 3)).toBe('abc');
  });
});
