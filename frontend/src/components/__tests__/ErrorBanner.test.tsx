import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ErrorBanner } from '../ErrorBanner';

describe('ErrorBanner', () => {
  it('renders the error message text', () => {
    render(<ErrorBanner message="Something went wrong" />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('has role="alert" for accessibility', () => {
    render(<ErrorBanner message="Network error" />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
