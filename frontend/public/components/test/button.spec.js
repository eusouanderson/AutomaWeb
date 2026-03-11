import { describe, expect, it, vi } from 'vitest';
import { createButton } from '../button.js';

describe('createButton', () => {
  it('creates a button element', () => {
    const btn = createButton({ label: 'Click me' });
    expect(btn.tagName).toBe('BUTTON');
  });

  it('sets the button text', () => {
    const btn = createButton({ label: 'Submit' });
    expect(btn.textContent).toBe('Submit');
  });

  it('applies default variant class', () => {
    const btn = createButton({ label: 'X' });
    expect(btn.className).toBe('btn btn-primary');
  });

  it('applies custom variant class', () => {
    const btn = createButton({ label: 'X', variant: 'secondary' });
    expect(btn.className).toBe('btn btn-secondary');
  });

  it('defaults type to button', () => {
    const btn = createButton({ label: 'X' });
    expect(btn.type).toBe('button');
  });

  it('sets custom type', () => {
    const btn = createButton({ label: 'X', type: 'submit' });
    expect(btn.type).toBe('submit');
  });

  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    const btn = createButton({ label: 'X', onClick });
    btn.click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not throw when onClick is not provided', () => {
    const btn = createButton({ label: 'X' });
    expect(() => btn.click()).not.toThrow();
  });
});
