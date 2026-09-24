/** 图片瀑布流的列分配。纯函数，便于单测与重排。 */

/** 设计稿断点：≥1280 六列，向下 4 / 3 / 2 列。 */
export function columnCount(containerWidth: number): number {
  if (containerWidth >= 1280) return 6;
  if (containerWidth >= 1024) return 4;
  if (containerWidth >= 640) return 3;
  return 2;
}

/**
 * 贪心最短列：依次把每个条目放进当前最矮的一列。
 * 返回与 heights 等长的列下标数组。
 */
export function distribute(heights: number[], columns: number): number[] {
  if (columns < 1) return heights.map(() => 0);

  const totals = new Array<number>(columns).fill(0);
  return heights.map((height) => {
    const safeHeight = Number.isFinite(height) && height > 0 ? height : 1;
    let target = 0;
    for (let index = 1; index < columns; index += 1) {
      const current = totals[index] ?? 0;
      const best = totals[target] ?? 0;
      if (current < best) target = index;
    }
    totals[target] = (totals[target] ?? 0) + safeHeight;
    return target;
  });
}

/** 按列下标把条目分组，保持原始顺序。 */
export function groupByColumn<T>(items: T[], assignments: number[], columns: number): T[][] {
  const buckets: T[][] = Array.from({ length: Math.max(columns, 1) }, () => []);
  items.forEach((item, index) => {
    const column = assignments[index] ?? 0;
    (buckets[column] ??= []).push(item);
  });
  return buckets;
}

/** 缺尺寸时用 4:3 兜底，避免初次渲染时高度塌陷。 */
export function estimateAspect(width: number | null, height: number | null): number {
  if (width && height && width > 0 && height > 0) {
    return Math.min(Math.max(width / height, 0.4), 2.5);
  }
  return 4 / 3;
}
