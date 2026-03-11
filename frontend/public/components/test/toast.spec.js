import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '../toast.js';

describe('toast', () => {
  let mockShowToast;
  let mockToastify;

  beforeEach(() => {
    mockShowToast = vi.fn();
    mockToastify = vi.fn().mockReturnValue({ showToast: mockShowToast });
    vi.stubGlobal('Toastify', mockToastify);
  });

  it('calls Toastify with the message text', () => {
    toast('Hello!');
    expect(mockToastify).toHaveBeenCalledWith(expect.objectContaining({ text: 'Hello!' }));
  });

  it('uses success color by default', () => {
    toast('ok');
    expect(mockToastify).toHaveBeenCalledWith(
      expect.objectContaining({ backgroundColor: '#0f766e' })
    );
  });

  it('uses error color for type "error"', () => {
    toast('bad', 'error');
    expect(mockToastify).toHaveBeenCalledWith(
      expect.objectContaining({ backgroundColor: '#b91c1c' })
    );
  });

  it('uses info color for type "info"', () => {
    toast('fyi', 'info');
    expect(mockToastify).toHaveBeenCalledWith(
      expect.objectContaining({ backgroundColor: '#1d4ed8' })
    );
  });

  it('falls back to info color for unknown types', () => {
    toast('weird', 'unknown');
    expect(mockToastify).toHaveBeenCalledWith(
      expect.objectContaining({ backgroundColor: '#1d4ed8' })
    );
  });

  it('calls showToast() on the returned instance', () => {
    toast('test');
    expect(mockShowToast).toHaveBeenCalledTimes(1);
  });

  it('sets duration, gravity, position and borderRadius', () => {
    toast('x');
    expect(mockToastify).toHaveBeenCalledWith(
      expect.objectContaining({
        duration: 3000,
        gravity: 'top',
        position: 'right',
        style: { borderRadius: '14px' }
      })
    );
  });
});
