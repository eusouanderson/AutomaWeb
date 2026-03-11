import { describe, expect, it } from 'vitest';
import { createLoader } from '../loader.js';

describe('createLoader', () => {
  it('returns a div element', () => {
    expect(createLoader().tagName).toBe('DIV');
  });

  it('has the "loader" CSS class', () => {
    expect(createLoader().className).toBe('loader');
  });

  it('uses the default label "Loading..."', () => {
    expect(createLoader().textContent).toContain('Loading...');
  });

  it('accepts a custom label', () => {
    expect(createLoader('Please wait').textContent).toContain('Please wait');
  });

  it('contains a loader-dot span', () => {
    expect(createLoader().querySelector('.loader-dot')).not.toBeNull();
  });

  it('loader-dot span is aria-hidden', () => {
    const dot = createLoader().querySelector('.loader-dot');
    expect(dot?.getAttribute('aria-hidden')).toBe('true');
  });
});
