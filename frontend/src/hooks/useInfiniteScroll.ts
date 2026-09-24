import { useEffect, useRef } from 'react';

/** 滚动到底部时触发加载下一页（游标分页，列表不做虚拟滚动）。 */
export function useInfiniteScroll(
  onLoadMore: () => void,
  options: { enabled: boolean; root?: HTMLElement | null },
) {
  const sentinel = useRef<HTMLDivElement | null>(null);
  const handler = useRef(onLoadMore);
  handler.current = onLoadMore;

  useEffect(() => {
    const node = sentinel.current;
    if (!options.enabled || !node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) handler.current();
      },
      { root: options.root ?? null, rootMargin: '240px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [options.enabled, options.root]);

  return sentinel;
}
