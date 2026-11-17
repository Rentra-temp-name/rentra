import type { CSSProperties } from "react";

const litWindows = new Set([1, 3, 4, 6, 8, 11, 12, 14, 16, 19, 21, 23]);

export function BrandPanel() {
  return (
    <aside className="brand-panel" aria-hidden="true">
      <div className="panel-brand">Rentra</div>
      <div className="building-facade">
        {Array.from({ length: 25 }, (_, index) => {
          const isLit = litWindows.has(index);
          const style = isLit
            ? ({ "--window-delay": `${0.35 + (index % 6) * 0.12}s` } as CSSProperties)
            : undefined;

          return (
            <span
              className={`facade-window${isLit ? " is-lit" : ""}${isLit && index % 3 === 0 ? " is-dim" : ""}`}
              key={index}
              style={style}
            />
          );
        })}
      </div>
      <h2>Find a place to live, or someone to live in yours.</h2>
    </aside>
  );
}
