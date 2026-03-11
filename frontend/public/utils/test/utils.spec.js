import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadTemplate, qs, qsa, renderHTML } from '../dom.js';
import { escapeHtml, formatDate, truncate } from '../helpers.js';
import { isValidUrl, requiredText } from '../validators.js';

describe('validators', () => {
  it('validates required text with min chars', () => {
    expect(requiredText('ab', 2)).toBe(true);
    expect(requiredText('a', 2)).toBe(false);
  });

  it('rejects non-string values', () => {
    expect(requiredText(null, 1)).toBe(false);
    expect(requiredText(undefined, 1)).toBe(false);
  });

  it('validates URL format', () => {
    expect(isValidUrl('https://example.com')).toBe(true);
    expect(isValidUrl('http://example.com')).toBe(true);
    expect(isValidUrl('ftp://example.com')).toBe(false);
    expect(isValidUrl('abc')).toBe(false);
    expect(isValidUrl('')).toBe(false);
    expect(isValidUrl(null)).toBe(false);
  });
});

describe('helpers', () => {
  describe('formatDate', () => {
    it('returns "-" for falsy values', () => {
      expect(formatDate(null)).toBe('-');
      expect(formatDate(undefined)).toBe('-');
      expect(formatDate('')).toBe('-');
    });

    it('returns a locale string for a valid date', () => {
      const result = formatDate('2024-01-15T10:00:00Z');
      expect(typeof result).toBe('string');
      expect(result.length).toBeGreaterThan(0);
      expect(result).not.toBe('-');
    });
  });

  describe('escapeHtml', () => {
    it('escapes html special chars', () => {
      expect(escapeHtml('<div>"x"</div>')).toBe('&lt;div&gt;&quot;x&quot;&lt;/div&gt;');
    });

    it('escapes ampersands and single quotes', () => {
      expect(escapeHtml("a & 'b'")).toBe('a &amp; &#39;b&#39;');
    });

    it('returns empty string when called with no argument', () => {
      expect(escapeHtml()).toBe('');
    });
  });

  describe('truncate', () => {
    it('truncates long strings', () => {
      expect(truncate('abcdef', 3)).toBe('abc...');
    });

    it('does not truncate strings within limit', () => {
      expect(truncate('abc', 3)).toBe('abc');
    });

    it('uses default limit 220', () => {
      const long = 'x'.repeat(221);
      expect(truncate(long)).toBe('x'.repeat(220) + '...');
    });

    it('returns empty string when called with no argument', () => {
      expect(truncate()).toBe('');
    });
  });
});

describe('dom', () => {
  let root;

  beforeEach(() => {
    root = document.createElement('div');
    root.innerHTML = '<p class="item">A</p><p class="item">B</p>';
    document.body.appendChild(root);
  });

  afterEach(() => {
    root.remove();
  });

  describe('qs', () => {
    it('returns first matching element', () => {
      expect(qs('.item', root)?.textContent).toBe('A');
    });

    it('returns null when no match', () => {
      expect(qs('.missing', root)).toBeNull();
    });

    it('uses document as default root', () => {
      expect(qs('body')).toBe(document.body);
    });
  });

  describe('qsa', () => {
    it('returns all matching elements as an array', () => {
      const items = qsa('.item', root);
      expect(items).toHaveLength(2);
      expect(items[0].textContent).toBe('A');
      expect(items[1].textContent).toBe('B');
    });

    it('returns an empty array when no match', () => {
      expect(qsa('.missing', root)).toEqual([]);
    });

    it('uses document as default root', () => {
      expect(Array.isArray(qsa('p'))).toBe(true);
    });
  });

  describe('renderHTML', () => {
    it('sets innerHTML on the root element', () => {
      const el = document.createElement('div');
      renderHTML(el, '<span>hello</span>');
      expect(el.innerHTML).toBe('<span>hello</span>');
    });

    it('replaces existing content', () => {
      const el = document.createElement('div');
      el.innerHTML = '<b>old</b>';
      renderHTML(el, '<i>new</i>');
      expect(el.querySelector('b')).toBeNull();
      expect(el.querySelector('i')).not.toBeNull();
    });
  });

  describe('loadTemplate', () => {
    beforeEach(() => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          text: vi.fn().mockResolvedValue('<section>template</section>')
        })
      );
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('fetches and returns the template HTML', async () => {
      const html = await loadTemplate('/unique-path-a.html');
      expect(html).toBe('<section>template</section>');
    });

    it('caches the result and does not fetch twice', async () => {
      await loadTemplate('/unique-path-b.html');
      await loadTemplate('/unique-path-b.html');
      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    });

    it('fetches again for a different path', async () => {
      await loadTemplate('/unique-path-c1.html');
      await loadTemplate('/unique-path-c2.html');
      expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    });
  });
});
