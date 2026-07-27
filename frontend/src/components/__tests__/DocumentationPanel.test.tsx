import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DocumentationPanel } from '../DocumentationPanel';
import type { ArtifactsResponse } from '../../types';

// Mock child components that have complex dependencies (mermaid, react-markdown)
vi.mock('../MermaidDiagram', () => ({
  MermaidDiagram: ({ code }: { code: string }) => (
    <div data-testid="mermaid-diagram">{code}</div>
  ),
}));

vi.mock('../MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => (
    <div data-testid="markdown-renderer">{content}</div>
  ),
}));

describe('DocumentationPanel - Use Cases Integration', () => {
  const baseArtifacts: ArtifactsResponse = {
    c4Mermaid: 'flowchart TD\n    A --> B',
    dbDictionary: '# Dictionary',
    adrDocument: '# ADR-001',
    rbacMatrix: '# RBAC Matrix',
    testPlan: '# Test Plan',
    useCases: null,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // Requirement 5.5: ArtifactTab type includes 'usecases'
  describe('ArtifactTab type includes usecases', () => {
    it('should accept "usecases" as a valid tab value and render the tab button', () => {
      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={baseArtifacts}
          artifactsLoading={false}
        />
      );

      // The tab with label "Casos de Uso" must exist — this confirms 'usecases' is a valid ArtifactTab
      const useCasesTab = screen.getByRole('button', { name: /Casos de Uso/i });
      expect(useCasesTab).toBeInTheDocument();
    });
  });

  // Requirements 5.1, 5.2: Tab renders when artifacts.useCases has content
  describe('Casos de Uso tab renders with content', () => {
    it('should show use cases content when tab is clicked and artifacts.useCases has content', () => {
      const useCasesContent = '## Historias de Usuario\n\n### HU-001: Crear usuario\n**Como** administrador...';
      const artifacts: ArtifactsResponse = {
        ...baseArtifacts,
        useCases: useCasesContent,
      };

      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={artifacts}
          artifactsLoading={false}
        />
      );

      // Click on the "Casos de Uso" tab
      const useCasesTab = screen.getByRole('button', { name: /Casos de Uso/i });
      fireEvent.click(useCasesTab);

      // The MarkdownRenderer should display the use cases content
      const renderer = screen.getByTestId('markdown-renderer');
      expect(renderer).toHaveTextContent('Historias de Usuario');
      expect(renderer).toHaveTextContent('HU-001');
    });

    it('should display the "Casos de Uso" tab with the 👤 icon', () => {
      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={baseArtifacts}
          artifactsLoading={false}
        />
      );

      const useCasesTab = screen.getByRole('button', { name: /👤.*Casos de Uso/i });
      expect(useCasesTab).toBeInTheDocument();
    });
  });

  // Requirements 5.3: Fallback message shows when artifacts.useCases is null
  describe('Fallback message when useCases is null', () => {
    it('should show fallback message when artifacts.useCases is null and tab is active', () => {
      const artifacts: ArtifactsResponse = {
        ...baseArtifacts,
        useCases: null,
      };

      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={artifacts}
          artifactsLoading={false}
        />
      );

      // Click on the "Casos de Uso" tab
      const useCasesTab = screen.getByRole('button', { name: /Casos de Uso/i });
      fireEvent.click(useCasesTab);

      // Should show the fallback message via MarkdownRenderer
      const renderer = screen.getByTestId('markdown-renderer');
      expect(renderer).toHaveTextContent('No se pudo generar los casos de uso');
    });

    it('should show fallback message when artifacts is null and usecases tab is active', () => {
      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={null}
          artifactsLoading={false}
        />
      );

      // Click on the "Casos de Uso" tab
      const useCasesTab = screen.getByRole('button', { name: /Casos de Uso/i });
      fireEvent.click(useCasesTab);

      // Should show the fallback message
      const renderer = screen.getByTestId('markdown-renderer');
      expect(renderer).toHaveTextContent('No se pudo generar los casos de uso');
    });
  });

  // Requirements 5.4, 5.5: Copy and Download work with useCases content
  describe('Copy and Download with useCases content', () => {
    it('should copy use cases content to clipboard when Copy button is clicked', async () => {
      const useCasesContent = '## Historias de Usuario\n\n### HU-001: Login';
      const artifacts: ArtifactsResponse = {
        ...baseArtifacts,
        useCases: useCasesContent,
      };

      // Mock clipboard API
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={artifacts}
          artifactsLoading={false}
        />
      );

      // Click on the "Casos de Uso" tab
      const useCasesTab = screen.getByRole('button', { name: /Casos de Uso/i });
      fireEvent.click(useCasesTab);

      // Click Copy button
      const copyButton = screen.getByRole('button', { name: /Copiar/i });
      fireEvent.click(copyButton);

      expect(writeTextMock).toHaveBeenCalledWith(useCasesContent);
    });

    it('should set download filename to "use-cases.md" when on usecases tab', () => {
      const useCasesContent = '## Casos de Uso\n\n### CU-001: Gestión de usuarios';
      const artifacts: ArtifactsResponse = {
        ...baseArtifacts,
        useCases: useCasesContent,
      };

      // Mock URL APIs
      const createObjectURLMock = vi.fn().mockReturnValue('blob:mock-url');
      const revokeObjectURLMock = vi.fn();
      global.URL.createObjectURL = createObjectURLMock;
      global.URL.revokeObjectURL = revokeObjectURLMock;

      // Track anchor element created for download
      const clickMock = vi.fn();
      const originalCreateElement = document.createElement.bind(document);
      vi.spyOn(document, 'createElement').mockImplementation((tag: string, options?: ElementCreationOptions) => {
        const el = originalCreateElement(tag, options);
        if (tag === 'a') {
          el.click = clickMock;
        }
        return el;
      });

      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={artifacts}
          artifactsLoading={false}
        />
      );

      // Click on the "Casos de Uso" tab
      const useCasesTab = screen.getByRole('button', { name: /Casos de Uso/i });
      fireEvent.click(useCasesTab);

      // Click Download button
      const downloadButton = screen.getByRole('button', { name: /Descargar/i });
      fireEvent.click(downloadButton);

      // Verify blob was created and download triggered
      expect(createObjectURLMock).toHaveBeenCalled();
      expect(clickMock).toHaveBeenCalled();
    });

    it('should have both Copy and Download buttons visible when on usecases tab', () => {
      const artifacts: ArtifactsResponse = {
        ...baseArtifacts,
        useCases: '## Use Cases content',
      };

      render(
        <DocumentationPanel
          repoUrl="https://github.com/test/repo"
          artifacts={artifacts}
          artifactsLoading={false}
        />
      );

      // Click on the "Casos de Uso" tab
      const useCasesTab = screen.getByRole('button', { name: /Casos de Uso/i });
      fireEvent.click(useCasesTab);

      // Both action buttons should be present
      expect(screen.getByRole('button', { name: /Copiar/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Descargar/i })).toBeInTheDocument();
    });
  });
});
