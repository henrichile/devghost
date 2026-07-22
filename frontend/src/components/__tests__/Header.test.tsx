import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Header } from '../Header';

describe('Header', () => {
  const defaultProps = {
    onAnalyze: vi.fn(),
    loading: false,
    repoUrl: '',
    onUrlChange: vi.fn(),
  };

  it('renders an input field and Analyze button', () => {
    render(<Header {...defaultProps} />);

    expect(screen.getByLabelText('Repository URL')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /analyze/i })).toBeInTheDocument();
  });

  it('button is disabled when input is empty', () => {
    render(<Header {...defaultProps} repoUrl="" />);

    expect(screen.getByRole('button', { name: /analyze/i })).toBeDisabled();
  });

  it('button is disabled when URL does not start with http:// or https://', () => {
    render(<Header {...defaultProps} repoUrl="ftp://example.com" />);

    expect(screen.getByRole('button', { name: /analyze/i })).toBeDisabled();
  });

  it('button is enabled when a valid URL is entered', () => {
    render(<Header {...defaultProps} repoUrl="https://github.com/user/repo" />);

    expect(screen.getByRole('button', { name: /analyze/i })).toBeEnabled();
  });

  it('button is disabled when loading prop is true', () => {
    render(
      <Header {...defaultProps} repoUrl="https://github.com/user/repo" loading={true} />
    );

    expect(screen.getByRole('button', { name: /analyze/i })).toBeDisabled();
  });

  it('calls onAnalyze with the URL on form submit', async () => {
    const onAnalyze = vi.fn();
    const user = userEvent.setup();

    render(
      <Header {...defaultProps} onAnalyze={onAnalyze} repoUrl="https://github.com/user/repo" />
    );

    await user.click(screen.getByRole('button', { name: /analyze/i }));

    expect(onAnalyze).toHaveBeenCalledWith('https://github.com/user/repo');
  });
});
