/** 可拖拽分栏的宽度计算与持久化。 */

export interface SplitConfig {
  /** 默认宽度（px） */
  fallback: number;
  min: number;
  max: number;
}

export const SIDEBAR_SPLIT: SplitConfig = { fallback: 288, min: 240, max: 480 };
export const LIST_SPLIT: SplitConfig = { fallback: 400, min: 280, max: 640 };
export const SIDEBAR_KEY = 'rss-tool:sidebar-width';
export const LIST_KEY = 'rss-tool:list-width';

export function clampWidth(value: number, config: SplitConfig): number {
  if (!Number.isFinite(value)) return config.fallback;
  return Math.min(Math.max(Math.round(value), config.min), config.max);
}

/** 拖拽位移 → 新宽度（向左拖变宽，用于左侧面板）。 */
export function widthFromDrag(
  startWidth: number,
  startX: number,
  currentX: number,
  config: SplitConfig,
): number {
  return clampWidth(startWidth + (currentX - startX), config);
}

export function loadWidth(key: string, config: SplitConfig, storage?: Storage): number {
  const store = storage ?? safeStorage();
  if (!store) return config.fallback;
  try {
    const raw = store.getItem(key);
    if (raw === null) return config.fallback;
    return clampWidth(Number.parseFloat(raw), config);
  } catch {
    return config.fallback;
  }
}

export function saveWidth(key: string, value: number, storage?: Storage): void {
  const store = storage ?? safeStorage();
  try {
    store?.setItem(key, String(Math.round(value)));
  } catch {
    // 隐私模式 / 配额满：宽度只是锦上添花，不值得打断交互
  }
}

/** 隐私模式 / SSR 下 localStorage 可能不可用，静默降级。 */
function safeStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** 分隔条的键盘步长。 */
export const KEYBOARD_STEP = 16;
