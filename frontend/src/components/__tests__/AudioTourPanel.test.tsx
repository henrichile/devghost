import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AudioTourPanel } from '../AudioTourPanel';

describe('AudioTourPanel', () => {
  beforeEach(() => {
    // Mock the Web Speech Synthesis API
    const mockSpeak = vi.fn();
    const mockCancel = vi.fn();

    Object.defineProperty(window, 'speechSynthesis', {
      value: {
        speak: mockSpeak,
        cancel: mockCancel,
        speaking: false,
        paused: false,
        pending: false,
        onvoiceschanged: null,
        getVoices: () => [],
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      },
      writable: true,
      configurable: true,
    });

    // Mock SpeechSynthesisUtterance
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      class MockUtterance {
        text = '';
        onend: (() => void) | null = null;
        onerror: (() => void) | null = null;
        constructor(text?: string) {
          this.text = text || '';
        }
      }
    );
  });

  it('renders "Play" button initially', () => {
    render(<AudioTourPanel summary="Test summary" />);

    expect(screen.getByRole('button', { name: /reproducir/i })).toBeInTheDocument();
  });

  it('shows summary text', () => {
    render(<AudioTourPanel summary="This is a test summary of the codebase." />);

    expect(screen.getByText('This is a test summary of the codebase.')).toBeInTheDocument();
  });

  it('clicking Play shows "Stop" button', async () => {
    const user = userEvent.setup();
    render(<AudioTourPanel summary="Test summary" />);

    await user.click(screen.getByRole('button', { name: /reproducir/i }));

    expect(screen.getByRole('button', { name: /detener/i })).toBeInTheDocument();
  });

  it('clicking Stop restores "Play" button', async () => {
    const user = userEvent.setup();
    render(<AudioTourPanel summary="Test summary" />);

    // Click Play first
    await user.click(screen.getByRole('button', { name: /reproducir/i }));
    expect(screen.getByRole('button', { name: /detener/i })).toBeInTheDocument();

    // Click Stop
    await user.click(screen.getByRole('button', { name: /detener/i }));
    expect(screen.getByRole('button', { name: /reproducir/i })).toBeInTheDocument();
  });
});
