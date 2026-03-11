import { describe, expect, it } from 'vitest';
import { createModal } from '../modal.js';

describe('createModal', () => {
  it('returns an element, open, and close', () => {
    const modal = createModal({ title: 'My Modal', content: '<p>Content</p>' });
    expect(modal.element).toBeInstanceOf(HTMLElement);
    expect(typeof modal.open).toBe('function');
    expect(typeof modal.close).toBe('function');
  });

  it('starts hidden', () => {
    const modal = createModal({ title: 'My Modal', content: '' });
    expect(modal.element.classList.contains('hidden')).toBe(true);
  });

  it('open removes hidden class', () => {
    const modal = createModal({ title: 'My Modal', content: '' });
    modal.open();
    expect(modal.element.classList.contains('hidden')).toBe(false);
  });

  it('close adds hidden class back', () => {
    const modal = createModal({ title: 'My Modal', content: '' });
    modal.open();
    modal.close();
    expect(modal.element.classList.contains('hidden')).toBe(true);
  });

  it('renders title text', () => {
    const modal = createModal({ title: 'Test Title', content: '' });
    const heading = modal.element.querySelector('h3');
    expect(heading?.textContent).toBe('Test Title');
  });

  it('renders string content as innerHTML', () => {
    const modal = createModal({ title: 'T', content: '<ul><li>Item</li></ul>' });
    const body = modal.element.querySelector('.modal-body');
    expect(body?.querySelector('ul')).not.toBeNull();
  });

  it('appends HTMLElement content', () => {
    const p = document.createElement('p');
    p.textContent = 'Hello';
    const modal = createModal({ title: 'T', content: p });
    const body = modal.element.querySelector('.modal-body');
    expect(body?.querySelector('p')?.textContent).toBe('Hello');
  });

  it('closes when clicking the close button', () => {
    const modal = createModal({ title: 'T', content: '' });
    modal.open();
    const closeBtn = modal.element.querySelector('[data-modal-close]');
    closeBtn?.click();
    expect(modal.element.classList.contains('hidden')).toBe(true);
  });

  it('closes when clicking the backdrop', () => {
    const modal = createModal({ title: 'T', content: '' });
    modal.open();
    modal.element.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(modal.element.classList.contains('hidden')).toBe(true);
  });
});
