import { describe, expect, it } from 'vitest';

import { columnCount, distribute, estimateAspect, groupByColumn } from './masonry';

describe('columnCount', () => {
  it('follows the design breakpoints', () => {
    expect(columnCount(1600)).toBe(6);
    expect(columnCount(1280)).toBe(6);
    expect(columnCount(1279)).toBe(4);
    expect(columnCount(1024)).toBe(4);
    expect(columnCount(1023)).toBe(3);
    expect(columnCount(640)).toBe(3);
    expect(columnCount(639)).toBe(2);
    expect(columnCount(320)).toBe(2);
  });
});

describe('distribute', () => {
  it('always assigns the first item to the first column', () => {
    expect(distribute([100, 100, 100], 3)).toEqual([0, 1, 2]);
  });

  it('puts each next item into the currently shortest column', () => {
    // 列高：0→[300] 1→[100] 2→[100] → 第二个 100 落进列 1（并列时取最小下标）
    expect(distribute([300, 100, 100, 50], 3)).toEqual([0, 1, 2, 1]);
  });

  it('balances a uniform list across columns', () => {
    const heights = new Array(12).fill(100);
    const columns = distribute(heights, 4);
    const totals = [0, 0, 0, 0];
    columns.forEach((column) => {
      totals[column] = (totals[column] ?? 0) + 100;
    });
    expect(totals).toEqual([300, 300, 300, 300]);
  });

  it('treats non-positive and invalid heights as 1', () => {
    expect(distribute([0, -5, Number.NaN], 3)).toEqual([0, 1, 2]);
  });

  it('returns one assignment per item', () => {
    expect(distribute([10, 20, 30, 40, 50], 5)).toHaveLength(5);
  });

  it('degrades to a single column when columns < 1', () => {
    expect(distribute([10, 20], 0)).toEqual([0, 0]);
  });

  it('reflows deterministically when the column count changes', () => {
    const heights = [300, 120, 220, 90, 260, 140];
    const six = distribute(heights, 6);
    const two = distribute(heights, 2);
    expect(six).toEqual([0, 1, 2, 3, 4, 5]);
    expect(two).toEqual(distribute(heights, 2));
    expect(Math.max(...two)).toBeLessThan(2);
  });
});

describe('groupByColumn', () => {
  it('preserves the original order inside each column', () => {
    const items = ['a', 'b', 'c', 'd'];
    expect(groupByColumn(items, [0, 1, 0, 1], 2)).toEqual([
      ['a', 'c'],
      ['b', 'd'],
    ]);
  });

  it('always returns the requested number of buckets', () => {
    expect(groupByColumn(['a'], [0], 3)).toHaveLength(3);
  });
});

describe('estimateAspect', () => {
  it('uses the real ratio when known', () => {
    expect(estimateAspect(1600, 800)).toBe(2);
  });

  it('clamps extreme ratios and falls back to 4:3', () => {
    expect(estimateAspect(100, 2000)).toBe(0.4);
    expect(estimateAspect(null, null)).toBeCloseTo(4 / 3);
    expect(estimateAspect(0, 100)).toBeCloseTo(4 / 3);
  });
});
