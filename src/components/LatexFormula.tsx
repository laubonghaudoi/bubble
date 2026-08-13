import { useEffect, useRef } from 'react';

let katexLoader: Promise<typeof import('katex')> | null = null;

function loadKatex() {
  katexLoader ??= Promise.all([
    import('katex'),
    import('katex/dist/katex.min.css'),
  ]).then(([module]) => module);
  return katexLoader;
}

interface LatexFormulaProps {
  tex: string;
  fallback: string;
  describedBy?: string;
  displayMode?: boolean;
  formulaId?: string;
}

export function LatexFormula({
  tex,
  fallback,
  describedBy,
  displayMode = true,
  formulaId,
}: LatexFormulaProps) {
  const formulaRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = formulaRef.current;
    if (!element) return;
    let cancelled = false;

    element.textContent = fallback;
    element.dataset.renderState = 'loading';
    delete element.dataset.renderError;

    loadKatex().then(({ default: katex }) => {
      if (cancelled) return;
      try {
        katex.render(tex, element, {
          displayMode,
          output: 'htmlAndMathml',
          throwOnError: true,
          strict: 'warn',
          trust: false,
        });
        element.dataset.renderState = 'rendered';
      } catch {
        element.textContent = fallback;
        element.dataset.renderState = 'fallback';
        element.dataset.renderError = 'true';
      }
    }).catch(() => {
      if (cancelled) return;
      element.textContent = fallback;
      element.dataset.renderState = 'fallback';
      element.dataset.renderError = 'true';
    });

    return () => { cancelled = true; };
  }, [displayMode, fallback, tex]);

  const attachFormula = (element: HTMLElement | null) => {
    formulaRef.current = element;
  };

  if (displayMode) {
    return <div className="latex-formula is-display" data-formula-id={formulaId} aria-describedby={describedBy} ref={attachFormula} />;
  }
  return <span className="latex-formula is-inline" data-formula-id={formulaId} aria-describedby={describedBy} ref={attachFormula} />;
}
