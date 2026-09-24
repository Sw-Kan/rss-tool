import { useCallback, useEffect, useRef, useState } from 'react';

import { KEYBOARD_STEP, clampWidth, saveWidth, widthFromDrag, type SplitConfig } from '../lib/split';

interface ResizerProps {
  width: number;
  onChange: (width: number) => void;
  config: SplitConfig;
  storageKey: string;
  label: string;
}

/** 可拖拽分隔条：Pointer Events + setPointerCapture，键盘 ←/→ 也可调。 */
export function Resizer({ width, onChange, config, storageKey, label }: ResizerProps) {
  const [dragging, setDragging] = useState(false);
  const origin = useRef({ x: 0, width: 0 });

  useEffect(() => {
    if (!dragging) return;
    const previousCursor = document.body.style.cursor;
    const previousSelect = document.body.style.userSelect;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousSelect;
    };
  }, [dragging]);

  const commit = useCallback(
    (next: number) => {
      onChange(next);
      saveWidth(storageKey, next);
    },
    [onChange, storageKey],
  );

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={config.min}
      aria-valuemax={config.max}
      tabIndex={0}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        origin.current = { x: event.clientX, width };
        setDragging(true);
      }}
      onPointerMove={(event) => {
        if (!dragging) return;
        commit(widthFromDrag(origin.current.width, origin.current.x, event.clientX, config));
      }}
      onPointerUp={(event) => {
        event.currentTarget.releasePointerCapture(event.pointerId);
        setDragging(false);
      }}
      onPointerCancel={() => setDragging(false)}
      onDoubleClick={() => commit(config.fallback)}
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          commit(clampWidth(width - KEYBOARD_STEP, config));
        } else if (event.key === 'ArrowRight') {
          event.preventDefault();
          commit(clampWidth(width + KEYBOARD_STEP, config));
        } else if (event.key === 'Home') {
          event.preventDefault();
          commit(config.fallback);
        }
      }}
      className="group relative w-[5px] cursor-col-resize touch-none"
    >
      <span
        className={`absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors ${
          dragging ? 'bg-brand' : 'bg-line group-hover:bg-brand'
        }`}
      />
    </div>
  );
}
