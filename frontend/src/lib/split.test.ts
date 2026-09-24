import { describe, expect, it } from 'vitest';

import {
  clampWidth,
  KEYBOARD_STEP,
  LIST_SPLIT,
  LIST_KEY,
  loadWidth,
  SIDEBAR_SPLIT,
  saveWidth,
  widthFromDrag,
} from './split';

/** 最小 Storage 实现，避免测试依赖 jsdom。 */
function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => void map.delete(key),
    setItem: (key: string, value: string) => void map.set(key, value),
  } as Storage;
}

describe('clampWidth', () => {
  it('keeps values inside the range', () => {
    expect(clampWidth(300, SIDEBAR_SPLIT)).toBe(300);
    expect(clampWidth(100, SIDEBAR_SPLIT)).toBe(240);
    expect(clampWidth(9999, SIDEBAR_SPLIT)).toBe(480);
  });

  it('rounds to whole pixels', () => {
    expect(clampWidth(300.6, SIDEBAR_SPLIT)).toBe(301);
  });

  it('falls back for invalid input', () => {
    expect(clampWidth(Number.NaN, SIDEBAR_SPLIT)).toBe(288);
    expect(clampWidth(Number.POSITIVE_INFINITY, SIDEBAR_SPLIT)).toBe(288);
  });

  it('respects each panel config', () => {
    expect(clampWidth(900, LIST_SPLIT)).toBe(640);
    expect(clampWidth(100, LIST_SPLIT)).toBe(280);
  });
});

describe('widthFromDrag', () => {
  it('grows when dragging right, shrinks when dragging left', () => {
    expect(widthFromDrag(288, 500, 560, SIDEBAR_SPLIT)).toBe(348);
    expect(widthFromDrag(288, 500, 460, SIDEBAR_SPLIT)).toBe(248);
  });

  it('clamps during the drag', () => {
    expect(widthFromDrag(288, 500, 1000, SIDEBAR_SPLIT)).toBe(480);
    expect(widthFromDrag(288, 500, 0, SIDEBAR_SPLIT)).toBe(240);
  });

  it('is identity when the pointer does not move', () => {
    expect(widthFromDrag(300, 400, 400, SIDEBAR_SPLIT)).toBe(300);
  });
});

describe('loadWidth / saveWidth', () => {
  it('round-trips through storage', () => {
    const storage = memoryStorage();
    saveWidth(LIST_KEY, 512.4, storage);
    expect(storage.getItem(LIST_KEY)).toBe('512');
    expect(loadWidth(LIST_KEY, LIST_SPLIT, storage)).toBe(512);
  });

  it('returns the default when nothing is stored', () => {
    expect(loadWidth(LIST_KEY, LIST_SPLIT, memoryStorage())).toBe(400);
  });

  it('clamps a stale or corrupted value', () => {
    const storage = memoryStorage();
    storage.setItem(LIST_KEY, '5000');
    expect(loadWidth(LIST_KEY, LIST_SPLIT, storage)).toBe(640);

    storage.setItem(LIST_KEY, 'garbage');
    expect(loadWidth(LIST_KEY, LIST_SPLIT, storage)).toBe(400);
  });

  it('degrades quietly when storage is unavailable or throws', () => {
    const broken = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
    } as unknown as Storage;

    expect(loadWidth(LIST_KEY, LIST_SPLIT, broken)).toBe(400);
    expect(() => saveWidth(LIST_KEY, 400, broken)).not.toThrow();
    expect(KEYBOARD_STEP).toBeGreaterThan(0);
  });
});
